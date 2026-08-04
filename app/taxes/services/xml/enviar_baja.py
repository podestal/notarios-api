from __future__ import annotations

import time
from pathlib import Path

import requests
from lxml import etree
from rest_framework.exceptions import ValidationError

from taxes.models import Bajas, Recibos

from .enviar_resumen import (
    _build_get_status_envelope,
    _build_send_summary_envelope,
    _extract_ticket,
    _parse_status_response,
    _save_exception,
)
from .enviar import (
    _create_zip,
    _extract_cdr_xml,
    _fault_message,
    _find_by_localname,
    _parse_cdr_fields,
    _post_send_bill,
    _sunat_credentials,
)
from .generar_baja import BajaXmlContext, fetch_baja_xml_context, generar_baja_xml
from .paths import (
    POSTGRES_DB,
    baja_firmar_path,
    ensure_output_dirs,
    summary_cdr_path,
    summary_cdr_zip_path,
    summary_status_soap_path,
    summary_ticket_path,
)


def _mark_baja_enviada(baja_id: int, *, archivo: str, ticket: str) -> None:
    Bajas.objects.using(POSTGRES_DB).filter(id_baja=baja_id).update(
        enviada_sunat=True,
        aceptada_sunat=False,
        ticket_sunat=ticket,
        denominacion=archivo,
    )


def _mark_baja_aceptada(baja_id: int, *, fields: dict) -> None:
    Bajas.objects.using(POSTGRES_DB).filter(id_baja=baja_id).update(
        aceptada_sunat=True,
        **fields,
    )
    Recibos.objects.using(POSTGRES_DB).filter(baja_id=baja_id).update(
        aceptada_sunat=False,
        enviada_sunat=False,
        error_sunat=None,
    )


def _mark_baja_rechazada(baja_id: int, *, fields: dict) -> None:
    Bajas.objects.using(POSTGRES_DB).filter(id_baja=baja_id).update(
        aceptada_sunat=False,
        **fields,
    )
    Recibos.objects.using(POSTGRES_DB).filter(baja_id=baja_id).update(
        aceptada_sunat=False,
        enviada_sunat=False,
    )


def _mark_recibos_baja_error(baja_id: int, *, error_message: str) -> None:
    Recibos.objects.using(POSTGRES_DB).filter(baja_id=baja_id).update(
        error_sunat=error_message[:2000],
    )


def enviar_baja_sunat(
    *,
    baja_id: int,
    ctx: BajaXmlContext | None = None,
    signed_path: Path | None = None,
    raise_on_failure: bool = False,
) -> dict:
    context = ctx or fetch_baja_xml_context(baja_id)
    ensure_output_dirs()
    archivo = context.archivo
    signed_xml_path = signed_path or baja_firmar_path(
        ruc=context.ruc_emisor,
        fecha_comunicacion=context.fecha_comunicacion,
        lote=context.lote,
    )
    if not signed_xml_path.is_file():
        raise ValidationError(f"XML firmado de baja no encontrado: {signed_xml_path}")

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
        soap_response = _post_send_bill(soap_xml, soap_action="urn:sendSummary")
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
    ticket_path = summary_ticket_path(archivo=archivo)
    ticket_path.write_bytes(soap_response)
    _mark_baja_enviada(baja_id, archivo=archivo, ticket=ticket)

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


def consultar_ticket_baja(
    *,
    baja_id: int,
    ticket: str | None = None,
    raise_on_failure: bool = False,
    max_polls: int = 1,
    poll_interval_seconds: float = 3.0,
) -> dict:
    baja = Bajas.objects.using(POSTGRES_DB).filter(id_baja=baja_id).first()
    if not baja:
        raise ValidationError("Baja no encontrada.")

    context = fetch_baja_xml_context(baja_id)
    archivo = context.archivo
    ticket_value = (ticket or baja.ticket_sunat or "").strip()
    if not ticket_value:
        raise ValidationError("La baja no tiene ticket SUNAT para consultar.")

    username, password = _sunat_credentials(ruc_emisor=context.ruc_emisor)
    last_result: dict = {}

    for attempt in range(max(1, max_polls)):
        soap_xml = _build_get_status_envelope(
            ticket=ticket_value,
            username=username,
            password=password,
        )
        try:
            soap_response = _post_send_bill(soap_xml, soap_action="urn:getStatus")
        except requests.RequestException as exc:
            error_message = f"Error de conexión con SUNAT: {exc}"
            if raise_on_failure:
                raise ValidationError(error_message) from exc
            return {
                "ticket": ticket_value,
                "cod_sunat": "",
                "msj_sunat": error_message,
                "enviada_sunat": bool(baja.enviada_sunat),
                "aceptada_sunat": False,
                "en_proceso": False,
            }

        parsed = _parse_status_response(soap_response)
        if parsed.get("en_proceso"):
            ensure_output_dirs()
            summary_status_soap_path(archivo=archivo).write_bytes(soap_response)
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
            _mark_baja_rechazada(baja_id, fields={})
            _mark_recibos_baja_error(baja_id, error_message=fault_message)
            return {
                "ticket": ticket_value,
                "cod_sunat": parsed.get("cod_sunat", ""),
                "msj_sunat": fault_message,
                "enviada_sunat": True,
                "aceptada_sunat": False,
                "en_proceso": False,
            }

        ensure_output_dirs()
        summary_status_soap_path(archivo=archivo).write_bytes(soap_response)
        summary_cdr_zip_path(archivo=archivo).write_bytes(parsed["cdr_zip_bytes"])

        cdr_xml = _extract_cdr_xml(
            cdr_zip_bytes=parsed["cdr_zip_bytes"],
            archivo=archivo,
            output_path=summary_cdr_path(archivo=archivo),
        )
        cdr_fields = _parse_cdr_fields(cdr_xml)
        update_fields = {
            "digest_value": cdr_fields["digest_value"] or baja.digest_value,
        }

        if cdr_fields["cod_sunat"] != "0":
            rejection_message = (
                f"SUNAT rechazó la baja ({cdr_fields['cod_sunat']}): "
                f"{cdr_fields['msj_sunat']}"
            )
            if raise_on_failure:
                raise ValidationError(rejection_message)
            _mark_baja_rechazada(baja_id, fields=update_fields)
            _mark_recibos_baja_error(baja_id, error_message=rejection_message)
            return {
                "ticket": ticket_value,
                "cod_sunat": cdr_fields["cod_sunat"],
                "msj_sunat": cdr_fields["msj_sunat"],
                "digest_value": cdr_fields["digest_value"],
                "enviada_sunat": True,
                "aceptada_sunat": False,
                "en_proceso": False,
                "cdr_path": str(summary_cdr_path(archivo=archivo)),
            }

        _mark_baja_aceptada(baja_id, fields=update_fields)
        return {
            "ticket": ticket_value,
            "cod_sunat": cdr_fields["cod_sunat"],
            "msj_sunat": cdr_fields["msj_sunat"],
            "digest_value": cdr_fields["digest_value"],
            "enviada_sunat": True,
            "aceptada_sunat": True,
            "en_proceso": False,
            "cdr_path": str(summary_cdr_path(archivo=archivo)),
        }

    return last_result


def procesar_baja_sunat(
    *,
    baja_id: int,
    max_polls: int = 10,
    poll_interval_seconds: float = 3.0,
    raise_on_failure: bool = False,
) -> dict:
    unsigned_path, ctx = generar_baja_xml(baja_id=baja_id)
    from .firmar import firmar_baja_xml

    signed_path = firmar_baja_xml(
        baja_id=baja_id,
        unsigned_path=unsigned_path,
        ctx=ctx,
    )
    send_result = enviar_baja_sunat(
        baja_id=baja_id,
        ctx=ctx,
        signed_path=signed_path,
        raise_on_failure=raise_on_failure,
    )
    result = {
        "generar": str(unsigned_path),
        "firmar": str(signed_path),
        "sunat_envio": send_result,
    }

    if send_result.get("ticket"):
        result["sunat_consulta"] = consultar_ticket_baja(
            baja_id=baja_id,
            ticket=send_result["ticket"],
            raise_on_failure=raise_on_failure,
            max_polls=max_polls,
            poll_interval_seconds=poll_interval_seconds,
        )
    return result
