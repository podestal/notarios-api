from __future__ import annotations

import base64
import time
from pathlib import Path

import requests
from lxml import etree
from rest_framework.exceptions import ValidationError

from taxes.models import Recibos, Resumenes

from .enviar import (
    _create_zip,
    _extract_cdr_xml,
    _fault_message,
    _find_by_localname,
    _parse_cdr_fields,
    _post_send_bill,
    _sunat_credentials,
)
from .generar_resumen import ResumenXmlContext, fetch_resumen_xml_context, generar_resumen_xml
from .paths import (
    POSTGRES_DB,
    ensure_output_dirs,
    exception_path,
    resumen_cdr_path,
    resumen_firmar_path,
    resumen_ticket_path,
)

SERVICE_NS = "http://service.sunat.gob.pe"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE_NS = (
    "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
)


def _build_soap_envelope(*, body_element: etree._Element, username: str, password: str) -> bytes:
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
    body.append(body_element)

    return etree.tostring(
        envelope,
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )


def _build_send_summary_envelope(
    *,
    file_name: str,
    zip_bytes: bytes,
    username: str,
    password: str,
) -> bytes:
    send_summary = etree.Element(f"{{{SERVICE_NS}}}sendSummary")
    etree.SubElement(send_summary, "fileName").text = file_name
    etree.SubElement(send_summary, "contentFile").text = base64.b64encode(zip_bytes).decode(
        "ascii"
    )
    return _build_soap_envelope(
        body_element=send_summary,
        username=username,
        password=password,
    )


def _build_get_status_envelope(*, ticket: str, username: str, password: str) -> bytes:
    get_status = etree.Element(f"{{{SERVICE_NS}}}getStatus")
    etree.SubElement(get_status, "ticket").text = ticket
    return _build_soap_envelope(
        body_element=get_status,
        username=username,
        password=password,
    )


def _save_exception(*, soap_response: bytes, archivo: str) -> Path:
    path = exception_path(archivo=archivo)
    path.write_bytes(soap_response)
    return path


def _extract_ticket(soap_response: bytes) -> str:
    root = etree.fromstring(soap_response)
    ticket_node = _find_by_localname(root, "ticket")
    if ticket_node is None or not ticket_node.text:
        raise ValidationError("SUNAT no devolvió ticket para el resumen.")
    return ticket_node.text.strip()


def _parse_status_response(soap_response: bytes) -> dict:
    root = etree.fromstring(soap_response)
    status_code_node = _find_by_localname(root, "statusCode")
    content_node = _find_by_localname(root, "content")

    status_code = (status_code_node.text or "").strip() if status_code_node is not None else ""
    content = (content_node.text or "").strip() if content_node is not None else ""

    if status_code in {"98", "0098"}:
        return {
            "status_code": status_code,
            "en_proceso": True,
            "cod_sunat": status_code,
            "msj_sunat": (
                "El proceso de aceptación de este resumen de comprobantes está pendiente."
            ),
            "enviada_sunat": True,
            "aceptada_sunat": False,
        }

    if not content:
        fault_message = _fault_message(soap_response)
        return {
            "status_code": status_code,
            "en_proceso": False,
            "cod_sunat": status_code,
            "msj_sunat": fault_message,
            "enviada_sunat": True,
            "aceptada_sunat": False,
        }

    cdr_zip_bytes = base64.b64decode(content)
    return {
        "status_code": status_code,
        "en_proceso": False,
        "cdr_zip_bytes": cdr_zip_bytes,
    }


def _mark_resumen_enviada(resumen_id: int, *, archivo: str, ticket: str) -> None:
    Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).update(
        enviada_sunat=True,
        aceptada_sunat=False,
        ticket_sunat=ticket,
        denominacion=archivo,
    )
    Recibos.objects.using(POSTGRES_DB).filter(
        resumen_id=resumen_id,
        anulada=False,
    ).update(enviada_sunat=True)
    Recibos.objects.using(POSTGRES_DB).filter(
        resumen_id=resumen_id,
        anulada=True,
    ).update(enviada_sunat=False, aceptada_sunat=False)


def _mark_resumen_aceptada(resumen_id: int, *, fields: dict) -> None:
    Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).update(
        aceptada_sunat=True,
        **fields,
    )


def _mark_resumen_rechazada(resumen_id: int, *, fields: dict) -> None:
    Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).update(
        aceptada_sunat=False,
        **fields,
    )


def _mark_recibos_aceptados(resumen_id: int) -> None:
    Recibos.objects.using(POSTGRES_DB).filter(
        resumen_id=resumen_id,
        anulada=False,
    ).update(
        enviada_sunat=True,
        aceptada_sunat=True,
        error_sunat=None,
    )
    Recibos.objects.using(POSTGRES_DB).filter(
        resumen_id=resumen_id,
        anulada=True,
    ).update(
        enviada_sunat=False,
        aceptada_sunat=False,
        error_sunat=None,
    )


def _mark_recibos_rechazados(resumen_id: int, *, error_message: str) -> None:
    Recibos.objects.using(POSTGRES_DB).filter(resumen_id=resumen_id).update(
        enviada_sunat=True,
        aceptada_sunat=False,
        error_sunat=error_message[:2000],
    )


def enviar_resumen_sunat(
    *,
    resumen_id: int,
    ctx: ResumenXmlContext | None = None,
    signed_path: Path | None = None,
    raise_on_failure: bool = False,
) -> dict:
    context = ctx or fetch_resumen_xml_context(resumen_id)
    resumen = Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).first()
    if not resumen:
        raise ValidationError("Resumen no encontrado.")

    ensure_output_dirs()
    archivo = context.archivo
    signed_xml_path = signed_path or resumen_firmar_path(
        ruc=context.ruc_emisor,
        fecha_comunicacion=context.fecha_comunicacion,
        lote=context.lote,
    )
    if not signed_xml_path.is_file():
        raise ValidationError(f"XML firmado de resumen no encontrado: {signed_xml_path}")

    username, password = _sunat_credentials(ruc_emisor=context.ruc_emisor)
    zip_path, zip_bytes = _create_zip(signed_xml_path=signed_xml_path, archivo=archivo)
    file_name = f"{archivo}.zip"
    soap_xml = _build_send_summary_envelope(
        file_name=file_name,
        zip_bytes=zip_bytes,
        username=username,
        password=password,
    )

    try:
        soap_response = _post_send_bill(soap_xml)
    except requests.RequestException as exc:
        error_message = f"Error de conexión con SUNAT: {exc}"
        if raise_on_failure:
            raise ValidationError(error_message) from exc
        return {
            "cod_sunat": "",
            "msj_sunat": error_message,
            "ticket": "",
            "enviada_sunat": False,
            "aceptada_sunat": False,
            "zip_path": str(zip_path),
        }

    response_root = etree.fromstring(soap_response)
    ticket_node = _find_by_localname(response_root, "ticket")
    if ticket_node is None or not ticket_node.text:
        exception_file = _save_exception(soap_response=soap_response, archivo=archivo)
        fault_message = _fault_message(soap_response)
        if raise_on_failure:
            raise ValidationError(fault_message)
        return {
            "cod_sunat": "",
            "msj_sunat": fault_message,
            "ticket": "",
            "enviada_sunat": False,
            "aceptada_sunat": False,
            "zip_path": str(zip_path),
            "exception_path": str(exception_file),
        }

    ticket = _extract_ticket(soap_response)
    ticket_path = resumen_ticket_path(archivo=archivo)
    ticket_path.write_bytes(soap_response)

    _mark_resumen_enviada(resumen_id, archivo=archivo, ticket=ticket)

    return {
        "ticket": ticket,
        "msj_sunat": ticket,
        "cod_sunat": "",
        "enviada_sunat": True,
        "aceptada_sunat": False,
        "zip_path": str(zip_path),
        "ticket_path": str(ticket_path),
        "archivo": archivo,
    }


def consultar_ticket_resumen(
    *,
    resumen_id: int,
    ticket: str | None = None,
    raise_on_failure: bool = False,
    max_polls: int = 1,
    poll_interval_seconds: float = 3.0,
) -> dict:
    resumen = Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).first()
    if not resumen:
        raise ValidationError("Resumen no encontrado.")

    context = fetch_resumen_xml_context(resumen_id)
    archivo = context.archivo
    ticket_value = (ticket or resumen.ticket_sunat or "").strip()
    if not ticket_value:
        raise ValidationError("El resumen no tiene ticket SUNAT para consultar.")

    username, password = _sunat_credentials(ruc_emisor=context.ruc_emisor)
    last_result: dict = {}

    for attempt in range(max(1, max_polls)):
        soap_xml = _build_get_status_envelope(
            ticket=ticket_value,
            username=username,
            password=password,
        )
        try:
            soap_response = _post_send_bill(soap_xml)
        except requests.RequestException as exc:
            error_message = f"Error de conexión con SUNAT: {exc}"
            if raise_on_failure:
                raise ValidationError(error_message) from exc
            return {
                "ticket": ticket_value,
                "cod_sunat": "",
                "msj_sunat": error_message,
                "enviada_sunat": bool(resumen.enviada_sunat),
                "aceptada_sunat": False,
                "en_proceso": False,
            }

        parsed = _parse_status_response(soap_response)
        if parsed.get("en_proceso"):
            last_result = {
                "ticket": ticket_value,
                "cod_sunat": parsed["cod_sunat"],
                "msj_sunat": parsed["msj_sunat"],
                "enviada_sunat": True,
                "aceptada_sunat": False,
                "en_proceso": True,
            }
            if attempt < max_polls - 1:
                time.sleep(poll_interval_seconds)
                continue
            if raise_on_failure:
                raise ValidationError(last_result["msj_sunat"])
            return last_result

        if "cdr_zip_bytes" not in parsed:
            fault_message = parsed.get("msj_sunat", "Error al consultar ticket SUNAT.")
            if raise_on_failure:
                raise ValidationError(fault_message)
            _mark_resumen_rechazada(resumen_id, fields={})
            _mark_recibos_rechazados(resumen_id, error_message=fault_message)
            return {
                "ticket": ticket_value,
                "cod_sunat": parsed.get("cod_sunat", ""),
                "msj_sunat": fault_message,
                "enviada_sunat": True,
                "aceptada_sunat": False,
                "en_proceso": False,
            }

        cdr_xml = _extract_cdr_xml(
            cdr_zip_bytes=parsed["cdr_zip_bytes"],
            archivo=archivo,
        )
        cdr_fields = _parse_cdr_fields(cdr_xml)
        update_fields = {
            "digest_value": cdr_fields["digest_value"] or resumen.digest_value,
        }

        if cdr_fields["cod_sunat"] != "0":
            rejection_message = (
                f"SUNAT rechazó el resumen ({cdr_fields['cod_sunat']}): "
                f"{cdr_fields['msj_sunat']}"
            )
            if raise_on_failure:
                raise ValidationError(rejection_message)
            _mark_resumen_rechazada(resumen_id, fields=update_fields)
            _mark_recibos_rechazados(resumen_id, error_message=rejection_message)
            return {
                "ticket": ticket_value,
                "cod_sunat": cdr_fields["cod_sunat"],
                "msj_sunat": cdr_fields["msj_sunat"],
                "digest_value": cdr_fields["digest_value"],
                "enviada_sunat": True,
                "aceptada_sunat": False,
                "en_proceso": False,
                "cdr_path": str(resumen_cdr_path(archivo=archivo)),
            }

        _mark_resumen_aceptada(resumen_id, fields=update_fields)
        _mark_recibos_aceptados(resumen_id)
        return {
            "ticket": ticket_value,
            "cod_sunat": cdr_fields["cod_sunat"],
            "msj_sunat": cdr_fields["msj_sunat"],
            "digest_value": cdr_fields["digest_value"],
            "enviada_sunat": True,
            "aceptada_sunat": True,
            "en_proceso": False,
            "cdr_path": str(resumen_cdr_path(archivo=archivo)),
        }

    return last_result


def procesar_resumen_sunat(
    *,
    resumen_id: int,
    consultar_ticket: bool = True,
    max_polls: int = 10,
    poll_interval_seconds: float = 3.0,
    raise_on_failure: bool = False,
) -> dict:
    unsigned_path, ctx = generar_resumen_xml(resumen_id=resumen_id)
    from .firmar import firmar_resumen_xml

    signed_path = firmar_resumen_xml(
        resumen_id=resumen_id,
        unsigned_path=unsigned_path,
        ctx=ctx,
    )
    send_result = enviar_resumen_sunat(
        resumen_id=resumen_id,
        ctx=ctx,
        signed_path=signed_path,
        raise_on_failure=raise_on_failure,
    )
    result = {
        "generar": str(unsigned_path),
        "firmar": str(signed_path),
        "sunat_envio": send_result,
    }

    if consultar_ticket and send_result.get("ticket"):
        result["sunat_consulta"] = consultar_ticket_resumen(
            resumen_id=resumen_id,
            ticket=send_result["ticket"],
            raise_on_failure=raise_on_failure,
            max_polls=max_polls,
            poll_interval_seconds=poll_interval_seconds,
        )
    return result
