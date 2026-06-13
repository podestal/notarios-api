from __future__ import annotations

import base64
import io
import os
import zipfile
from pathlib import Path

import requests
from lxml import etree
from rest_framework.exceptions import ValidationError

from taxes.models import Recibos
from taxes.services.control_interno import BOLETA_COMPROBANTE_ID

from .context import ReciboXmlContext, fetch_recibo_xml_context
from .paths import (
    POSTGRES_DB,
    cdr_path,
    ensure_output_dirs,
    exception_path,
    firmar_path,
)

DEFAULT_SUNAT_WS_URL = (
    "https://e-beta.sunat.gob.pe/ol-ti-itcpfegem-beta/billService"
)
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
SERVICE_NS = "http://service.sunat.gob.pe"
WSSE_NS = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
)


def should_auto_enviar_sunat(ctx: ReciboXmlContext) -> bool:
    codigo = ctx.codigo_comprobante
    if codigo == "01":
        return True
    if codigo in ("07", "08"):
        return ctx.codigo_recibo_modificado == "01"
    return False


def can_enviar_recibo_sunat(ctx: ReciboXmlContext) -> bool:
    if ctx.id_comprobante == BOLETA_COMPROBANTE_ID:
        return False
    return should_auto_enviar_sunat(ctx)


def _localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _find_by_localname(root: etree._Element, name: str) -> etree._Element | None:
    for element in root.iter():
        if _localname(element.tag) == name:
            return element
    return None


def _sunat_credentials(*, ruc_emisor: str) -> tuple[str, str]:
    username = os.environ.get("SUNAT_SOL_USERNAME", "").strip()
    password = (
        os.environ.get("SUNAT_SOL_PASSWORD")
        or os.environ.get("PASS_CLAVE_SOL")
        or ""
    ).strip()
    sol_user = (
        os.environ.get("SUNAT_SOL_USER")
        or os.environ.get("USER_CLAVE_SOL")
        or ""
    ).strip()
    ruc_sol = (
        os.environ.get("SUNAT_RUC_SOL")
        or os.environ.get("RUC_CLAVE_SOL")
        or ""
    ).strip()

    if not username and sol_user:
        ruc = ruc_sol or ruc_emisor
        username = f"{ruc}{sol_user}"

    if not username or not password:
        raise ValidationError(
            "Configura SUNAT_SOL_USERNAME y SUNAT_SOL_PASSWORD "
            "(o RUC_CLAVE_SOL + USER_CLAVE_SOL + PASS_CLAVE_SOL) "
            "para enviar comprobantes a SUNAT."
        )
    return username, password


def _sunat_ws_url() -> str:
    return (
        os.environ.get("SUNAT_WS_URL")
        or os.environ.get("WEB_SERVICE_SUNAT")
        or DEFAULT_SUNAT_WS_URL
    ).strip()


def _create_zip(*, signed_xml_path: Path, archivo: str) -> tuple[Path, bytes]:
    zip_path = signed_xml_path.with_suffix(".ZIP")
    xml_entry_name = f"{archivo}.XML"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(signed_xml_path, arcname=xml_entry_name)

    return zip_path, zip_path.read_bytes()


def _build_send_bill_envelope(
    *,
    file_name: str,
    zip_bytes: bytes,
    username: str,
    password: str,
) -> bytes:
    envelope = etree.Element(
        f"{{{SOAP_NS}}}Envelope",
        nsmap={
            "soapenv": SOAP_NS,
            "ser": SERVICE_NS,
            "wsse": WSSE_NS,
        },
    )
    header = etree.SubElement(envelope, f"{{{SOAP_NS}}}Header")
    security = etree.SubElement(header, f"{{{WSSE_NS}}}Security")
    token = etree.SubElement(security, f"{{{WSSE_NS}}}UsernameToken")
    etree.SubElement(token, f"{{{WSSE_NS}}}Username").text = username
    etree.SubElement(token, f"{{{WSSE_NS}}}Password").text = password

    body = etree.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    send_bill = etree.SubElement(body, f"{{{SERVICE_NS}}}sendBill")
    etree.SubElement(send_bill, "fileName").text = file_name
    etree.SubElement(send_bill, "contentFile").text = base64.b64encode(zip_bytes).decode(
        "ascii"
    )

    return etree.tostring(
        envelope,
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )


def _post_send_bill(soap_xml: bytes) -> bytes:
    response = requests.post(
        _sunat_ws_url(),
        data=soap_xml,
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "urn:sendBill",
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.content


def _extract_cdr_xml(*, cdr_zip_bytes: bytes, archivo: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(cdr_zip_bytes)) as archive:
        xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        if not xml_names:
            raise ValidationError("El CDR de SUNAT no contiene un archivo XML.")
        cdr_xml = archive.read(xml_names[0])

    output_path = cdr_path(archivo=archivo)
    output_path.write_bytes(cdr_xml)
    return cdr_xml


def _parse_cdr_fields(cdr_xml: bytes) -> dict[str, str]:
    root = etree.fromstring(cdr_xml)
    response_code = _find_by_localname(root, "ResponseCode")
    description = _find_by_localname(root, "Description")
    digest_value = _find_by_localname(root, "DigestValue")
    return {
        "cod_sunat": (response_code.text or "").strip() if response_code is not None else "",
        "msj_sunat": (description.text or "").strip() if description is not None else "",
        "digest_value": (digest_value.text or "").strip() if digest_value is not None else "",
    }


def _save_exception(*, soap_response: bytes, archivo: str) -> Path:
    path = exception_path(archivo=archivo)
    path.write_bytes(soap_response)
    return path


def _fault_message(soap_response: bytes) -> str:
    root = etree.fromstring(soap_response)
    fault_string = _find_by_localname(root, "faultstring")
    if fault_string is not None and fault_string.text:
        return fault_string.text.strip()
    return "Error SOAP al enviar comprobante a SUNAT."


def _mark_enviada(recibo_id: int) -> None:
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).update(
        enviada_sunat=True,
    )


def _mark_aceptada(recibo_id: int, *, fields: dict) -> None:
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).update(
        aceptada_sunat=True,
        **fields,
    )


def _mark_rechazada(recibo_id: int, *, fields: dict) -> None:
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).update(
        aceptada_sunat=False,
        **fields,
    )


def _mark_error_sunat(recibo_id: int, *, error_message: str) -> None:
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).update(
        enviada_sunat=False,
        aceptada_sunat=False,
        error_sunat=error_message[:2000],
    )


def enviar_recibo_sunat(
    *,
    recibo_id: int,
    ctx: ReciboXmlContext | None = None,
    signed_path: Path | None = None,
) -> dict:
    context = ctx or fetch_recibo_xml_context(recibo_id)
    if not can_enviar_recibo_sunat(context):
        if context.id_comprobante == BOLETA_COMPROBANTE_ID:
            raise ValidationError(
                "Las boletas se envían a SUNAT mediante resumen diario, no individualmente."
            )
        raise ValidationError(
            "Este comprobante no debe enviarse individualmente a SUNAT."
        )

    recibo = Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).first()
    if not recibo:
        raise ValidationError("Recibo no encontrado.")

    ensure_output_dirs()
    archivo = context.nombre_comprobante
    signed_xml_path = signed_path or firmar_path(
        ruc=context.ruc_emisor,
        codigo_comprobante=context.codigo_comprobante,
        serie=context.serie,
        numero=context.numero,
    )
    if not signed_xml_path.is_file():
        raise ValidationError(f"XML firmado no encontrado: {signed_xml_path}")

    username, password = _sunat_credentials(ruc_emisor=context.ruc_emisor)
    zip_path, zip_bytes = _create_zip(signed_xml_path=signed_xml_path, archivo=archivo)
    file_name = f"{archivo}.zip"
    soap_xml = _build_send_bill_envelope(
        file_name=file_name,
        zip_bytes=zip_bytes,
        username=username,
        password=password,
    )

    try:
        soap_response = _post_send_bill(soap_xml)
    except requests.RequestException as exc:
        error_message = f"Error de conexión con SUNAT: {exc}"
        _mark_error_sunat(recibo_id, error_message=error_message)
        return {
            "cod_sunat": "",
            "msj_sunat": error_message,
            "enviada_sunat": False,
            "aceptada_sunat": False,
            "zip_path": str(zip_path),
        }

    response_root = etree.fromstring(soap_response)
    application_response = _find_by_localname(response_root, "applicationResponse")

    if application_response is None or not application_response.text:
        exception_file = _save_exception(soap_response=soap_response, archivo=archivo)
        fault_message = _fault_message(soap_response)
        _mark_error_sunat(recibo_id, error_message=fault_message)
        return {
            "cod_sunat": "",
            "msj_sunat": fault_message,
            "enviada_sunat": False,
            "aceptada_sunat": False,
            "zip_path": str(zip_path),
            "exception_path": str(exception_file),
        }

    cdr_zip_bytes = base64.b64decode(application_response.text)
    cdr_xml = _extract_cdr_xml(cdr_zip_bytes=cdr_zip_bytes, archivo=archivo)
    cdr_fields = _parse_cdr_fields(cdr_xml)

    update_fields = {
        "observaciones_sunat": cdr_fields["msj_sunat"][:2000] or None,
        "codigo_error": cdr_fields["cod_sunat"] or None,
        "error_sunat": None,
    }
    if cdr_fields["digest_value"]:
        update_fields["digest_value"] = cdr_fields["digest_value"]

    _mark_enviada(recibo_id)

    anulada = bool(recibo.anulada)
    if cdr_fields["cod_sunat"] == "0" and not anulada:
        _mark_aceptada(recibo_id, fields=update_fields)
        aceptada = True
    else:
        _mark_rechazada(recibo_id, fields=update_fields)
        aceptada = False

    return {
        "cod_sunat": cdr_fields["cod_sunat"],
        "msj_sunat": cdr_fields["msj_sunat"],
        "digest_value": cdr_fields["digest_value"],
        "enviada_sunat": True,
        "aceptada_sunat": aceptada,
        "zip_path": str(zip_path),
        "cdr_path": str(cdr_path(archivo=archivo)),
    }
