from __future__ import annotations

import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)
from cryptography.x509.oid import NameOID
from lxml import etree
from rest_framework.exceptions import ValidationError
from signxml import XMLSigner, methods

try:
    from signxml import DigestAlgorithm, SignatureMethod
except ImportError:
    DigestAlgorithm = None  # type: ignore[misc, assignment]
    SignatureMethod = None  # type: ignore[misc, assignment]


class SunatXMLSigner(XMLSigner):
    """SUNAT legacy Firmador uses RSA-SHA1; signxml blocks it unless overridden."""

    def check_deprecated_methods(self) -> None:
        return

from taxes.models import Recibos

from .context import ReciboXmlContext, fetch_recibo_xml_context
from .paths import POSTGRES_DB, ensure_output_dirs, firmar_path, generar_path

UBL_EXTENSION_NS = (
    "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
)
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SIGNATURE_PLACEHOLDER_ID = "placeholder"
SIGNATURE_ID = "SignSUNAT"

_OID_SHORT_NAMES = {
    NameOID.COMMON_NAME: "CN",
    NameOID.ORGANIZATIONAL_UNIT_NAME: "OU",
    NameOID.ORGANIZATION_NAME: "O",
    NameOID.LOCALITY_NAME: "L",
    NameOID.STATE_OR_PROVINCE_NAME: "ST",
    NameOID.COUNTRY_NAME: "C",
    NameOID.ORGANIZATION_IDENTIFIER: "organizationIdentifier",
}


def _load_signing_material() -> tuple[bytes, bytes]:
    cert_path = (
        os.environ.get("SUNAT_XML_CERTIFICATE_PATH")
        or os.environ.get("SUNAT_XML_CERT_PATH")
        or os.environ.get("CLAVE_PUBLICA")
    )
    key_path = (
        os.environ.get("SUNAT_XML_PRIVATE_KEY_PATH")
        or os.environ.get("SUNAT_XML_KEY_PATH")
        or os.environ.get("CLAVE_PRIVADA")
    )
    pfx_path = os.environ.get("SUNAT_XML_PFX_PATH")
    pfx_password = os.environ.get("SUNAT_XML_PFX_PASSWORD", "")

    if pfx_path:
        pfx_bytes = Path(pfx_path).expanduser().read_bytes()
        private_key, certificate, _additional = pkcs12.load_key_and_certificates(
            pfx_bytes,
            pfx_password.encode("utf-8") if pfx_password else None,
        )
        if private_key is None or certificate is None:
            raise ValidationError("No se pudo leer la clave o el certificado del PFX.")
        key_pem = private_key.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
        cert_pem = certificate.public_bytes(Encoding.PEM)
        return key_pem, cert_pem

    if not cert_path or not key_path:
        raise ValidationError(
            "Configura SUNAT_XML_CERTIFICATE_PATH y SUNAT_XML_PRIVATE_KEY_PATH "
            "(o SUNAT_XML_PFX_PATH) para firmar comprobantes."
        )

    return (
        Path(key_path).expanduser().read_bytes(),
        Path(cert_path).expanduser().read_bytes(),
    )


def _certificate_subject_name(cert_pem: bytes) -> str:
    cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
    parts = []
    for attribute in cert.subject:
        short_name = _OID_SHORT_NAMES.get(attribute.oid, attribute.oid.dotted_string)
        parts.append(f"{short_name}={attribute.value}")
    return ",".join(parts)


def _ensure_signature_placeholder(root: etree._Element) -> None:
    extension_content = root.find(f".//{{{UBL_EXTENSION_NS}}}ExtensionContent")
    if extension_content is None:
        raise ValidationError("No se encontró ext:ExtensionContent en el XML.")

    for child in extension_content:
        if child.tag == f"{{{DS_NS}}}Signature":
            return

    etree.SubElement(
        extension_content,
        f"{{{DS_NS}}}Signature",
        Id=SIGNATURE_PLACEHOLDER_ID,
    )


def _apply_legacy_signature_format(root: etree._Element, *, cert_pem: bytes) -> None:
    signature = root.find(f".//{{{DS_NS}}}Signature")
    if signature is None:
        return

    signature.set("Id", SIGNATURE_ID)

    x509_data = signature.find(f".//{{{DS_NS}}}X509Data")
    if x509_data is None:
        return

    if x509_data.find(f"{{{DS_NS}}}X509SubjectName") is not None:
        return

    subject_node = etree.Element(f"{{{DS_NS}}}X509SubjectName")
    subject_node.text = _certificate_subject_name(cert_pem)
    x509_data.insert(0, subject_node)


def _extract_digest_value(signed_xml: bytes) -> str:
    root = etree.fromstring(signed_xml)
    digest_nodes = root.xpath("//*[local-name()='DigestValue']")
    if not digest_nodes:
        raise ValidationError("No se encontró DigestValue en el XML firmado.")
    return digest_nodes[0].text or ""


def firmar_recibo_xml(
    *,
    recibo_id: int,
    ctx: ReciboXmlContext | None = None,
    unsigned_path: Path | None = None,
) -> Path:
    context = ctx or fetch_recibo_xml_context(recibo_id)
    ensure_output_dirs()

    source_path = unsigned_path or generar_path(
        ruc=context.ruc_emisor,
        codigo_comprobante=context.codigo_comprobante,
        serie=context.serie,
        numero=context.numero,
    )
    if not source_path.is_file():
        raise ValidationError(f"XML sin firmar no encontrado: {source_path}")

    unsigned_xml = source_path.read_bytes()
    key_pem, cert_pem = _load_signing_material()

    signature_algorithm = (
        SignatureMethod.RSA_SHA1 if SignatureMethod else "rsa-sha1"
    )
    digest_algorithm = DigestAlgorithm.SHA1 if DigestAlgorithm else "sha1"
    signer = SunatXMLSigner(
        method=methods.enveloped,
        signature_algorithm=signature_algorithm,
        digest_algorithm=digest_algorithm,
        c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#",
    )
    root = etree.fromstring(unsigned_xml)
    _ensure_signature_placeholder(root)

    signed_root = signer.sign(
        root,
        key=key_pem,
        cert=cert_pem,
        exclude_c14n_transform_element=True,
    )
    _apply_legacy_signature_format(signed_root, cert_pem=cert_pem)

    signed_xml = etree.tostring(
        signed_root,
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )

    output_path = firmar_path(
        ruc=context.ruc_emisor,
        codigo_comprobante=context.codigo_comprobante,
        serie=context.serie,
        numero=context.numero,
    )
    output_path.write_bytes(signed_xml)

    digest_value = _extract_digest_value(signed_xml)
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).update(
        digest_value=digest_value,
        nombre_comprobante=context.nombre_comprobante,
    )
    return output_path
