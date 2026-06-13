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

RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"
C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
XML_DECLARATION = b'<?xml version="1.0" encoding="UTF-8"?>'


class SunatXMLSigner(XMLSigner):
    """SUNAT legacy Firmador uses RSA-SHA1; signxml blocks it unless overridden."""

    def check_deprecated_methods(self) -> None:
        return


from taxes.models import Recibos, Resumenes

from .context import ReciboXmlContext, fetch_recibo_xml_context
from .paths import POSTGRES_DB, ensure_output_dirs, firmar_path, generar_path, resumen_generar_path

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


def _prepare_extension_content_for_signing(root: etree._Element) -> etree._Element:
    extension_content = root.find(f".//{{{UBL_EXTENSION_NS}}}ExtensionContent")
    if extension_content is None:
        raise ValidationError("No se encontró ext:ExtensionContent en el XML.")

    extension_content.text = None
    extension_content.tail = None
    for child in list(extension_content):
        extension_content.remove(child)
    return extension_content


def _ensure_signature_placeholder(root: etree._Element) -> None:
    extension_content = _prepare_extension_content_for_signing(root)

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


def _normalize_signed_xml_bytes(signed_xml: bytes) -> bytes:
    if signed_xml.startswith(b"<?xml"):
        _, _, body = signed_xml.partition(b"?>")
        signed_xml = body.lstrip(b"\n\r")
    return XML_DECLARATION + b"\n" + signed_xml


def _validate_signed_xml(signed_xml: bytes) -> None:
    root = etree.fromstring(signed_xml)
    signature_method = root.find(f".//{{{DS_NS}}}SignatureMethod")
    algorithm = (
        (signature_method.get("Algorithm") or "").strip()
        if signature_method is not None
        else ""
    )
    if not algorithm:
        raise ValidationError(
            "El XML firmado no contiene SignatureMethod; la firma SUNAT no se generó correctamente."
        )


def _extract_digest_value(signed_xml: bytes) -> str:
    root = etree.fromstring(signed_xml)
    digest_nodes = root.xpath("//*[local-name()='DigestValue']")
    if not digest_nodes:
        raise ValidationError("No se encontró DigestValue en el XML firmado.")
    return digest_nodes[0].text or ""


def _extract_signature_value(signed_xml: bytes) -> str:
    root = etree.fromstring(signed_xml)
    signature_nodes = root.xpath("//*[local-name()='SignatureValue']")
    if not signature_nodes:
        raise ValidationError("No se encontró SignatureValue en el XML firmado.")
    return signature_nodes[0].text or ""


def firmar_xml_document(
    *,
    unsigned_path: Path,
    output_path: Path,
) -> tuple[Path, str, str]:
    if not unsigned_path.is_file():
        raise ValidationError(f"XML sin firmar no encontrado: {unsigned_path}")

    unsigned_xml = unsigned_path.read_bytes()
    key_pem, cert_pem = _load_signing_material()

    signer = SunatXMLSigner(
        method=methods.enveloped,
        signature_algorithm=RSA_SHA1,
        digest_algorithm=SHA1,
        c14n_algorithm=C14N,
    )
    parser = etree.XMLParser(remove_blank_text=False, strip_cdata=False)
    root = etree.fromstring(unsigned_xml, parser=parser)
    _ensure_signature_placeholder(root)

    signed_root = signer.sign(
        root,
        key=key_pem,
        cert=cert_pem,
    )
    _apply_legacy_signature_format(signed_root, cert_pem=cert_pem)

    signed_xml = _normalize_signed_xml_bytes(
        etree.tostring(
            signed_root,
            encoding="UTF-8",
            xml_declaration=False,
            pretty_print=False,
        )
    )

    _validate_signed_xml(signed_xml)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(signed_xml)

    digest_value = _extract_digest_value(signed_xml)
    signature_value = _extract_signature_value(signed_xml)
    return output_path, digest_value, signature_value


def firmar_resumen_xml(
    *,
    resumen_id: int,
    unsigned_path: Path | None = None,
    ctx: "ResumenXmlContext | None" = None,
) -> Path:
    from .generar_resumen import fetch_resumen_xml_context
    from .paths import resumen_firmar_path

    context = ctx or fetch_resumen_xml_context(resumen_id)
    ensure_output_dirs()

    source_path = unsigned_path or resumen_generar_path(
        ruc=context.ruc_emisor,
        fecha_comunicacion=context.fecha_comunicacion,
        lote=context.lote,
    )
    output_path = resumen_firmar_path(
        ruc=context.ruc_emisor,
        fecha_comunicacion=context.fecha_comunicacion,
        lote=context.lote,
    )

    signed_path, digest_value, signature_value = firmar_xml_document(
        unsigned_path=source_path,
        output_path=output_path,
    )
    Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).update(
        digest_value=digest_value,
        signature_value=signature_value,
        denominacion=context.archivo,
    )
    return signed_path


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

    output_path = firmar_path(
        ruc=context.ruc_emisor,
        codigo_comprobante=context.codigo_comprobante,
        serie=context.serie,
        numero=context.numero,
    )
    signed_path, digest_value, _signature_value = firmar_xml_document(
        unsigned_path=source_path,
        output_path=output_path,
    )
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).update(
        digest_value=digest_value,
        nombre_comprobante=context.nombre_comprobante,
    )
    return signed_path
