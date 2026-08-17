from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from taxes.legacy_db import next_serial_id
from taxes.models import Documentos, Personas, Usuarios

POSTGRES_DB = "postgres"
User = get_user_model()

DEFAULT_ESTADO = 1
DEFAULT_ROL_ID = 1
DNI_DOCUMENTO_CODIGO = "1"


def _now():
    return timezone.localtime().replace(tzinfo=None)


def _blank(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_nombre_completo(
    *,
    nombres: str = "",
    apellido_paterno: str = "",
    apellido_materno: str = "",
    razon_social: str = "",
    nombre_completo: str = "",
) -> str:
    if _blank(nombre_completo):
        return _blank(nombre_completo)
    parts = [
        _blank(nombres),
        _blank(apellido_paterno),
        _blank(apellido_materno),
    ]
    joined = " ".join(part for part in parts if part)
    if joined:
        return joined
    if _blank(razon_social):
        return _blank(razon_social)
    raise ValidationError(
        {"persona": "Send nombres or razon_social."}
    )


def resolve_documento_id(documento_id: int | None) -> int:
    if documento_id is not None:
        if not Documentos.objects.using(POSTGRES_DB).filter(
            id_documento=documento_id
        ).exists():
            raise ValidationError(f"documento={documento_id} no existe.")
        return documento_id

    dni = (
        Documentos.objects.using(POSTGRES_DB)
        .filter(codigo__in=[DNI_DOCUMENTO_CODIGO, "01"])
        .values_list("id_documento", flat=True)
        .first()
    )
    if dni is None:
        raise ValidationError(
            "documento is required (could not default to DNI, codigo='1')."
        )
    return dni


def _create_persona(data: dict) -> Personas:
    numero_documento = _blank(data.get("numero_documento"))
    if not numero_documento:
        raise ValidationError({"persona": {"numero_documento": "This field is required."}})

    existing = (
        Personas.objects.using(POSTGRES_DB)
        .filter(numero_documento=numero_documento)
        .first()
    )
    if existing is not None:
        raise ValidationError(
            {
                "persona": {
                    "numero_documento": (
                        f"Already registered as persona_id={existing.id_persona} "
                        f"({existing.nombre_completo})."
                    )
                }
            }
        )

    nombres = _blank(data.get("nombres"))
    apellido_paterno = _blank(data.get("apellido_paterno"))
    apellido_materno = _blank(data.get("apellido_materno"))
    razon_social = _blank(data.get("razon_social"))
    nombre_completo = build_nombre_completo(
        nombres=nombres,
        apellido_paterno=apellido_paterno,
        apellido_materno=apellido_materno,
        razon_social=razon_social,
        nombre_completo=_blank(data.get("nombre_completo")),
    )
    now = _now()
    return Personas.objects.using(POSTGRES_DB).create(
        id_persona=next_serial_id("personas", "id_persona"),
        nombres=nombres or None,
        apellido_paterno=apellido_paterno or None,
        apellido_materno=apellido_materno or None,
        razon_social=razon_social or None,
        nombre_comercial=_blank(data.get("nombre_comercial")) or None,
        documento_id=resolve_documento_id(data.get("documento")),
        numero_documento=numero_documento,
        direccion=_blank(data.get("direccion")) or None,
        fecha_nacimiento=data.get("fecha_nacimiento"),
        nombre_completo=nombre_completo,
        email=_blank(data.get("email")) or None,
        creado=now,
        actualizado=now,
    )


def _link_core_user(*, idusuario: int, taxes_user: Usuarios) -> User:
    core_user = User.objects.filter(idusuario=idusuario).first()
    if core_user is None:
        raise ValidationError(f"idusuario={idusuario} no existe.")
    if (
        core_user.taxes_usuario_id
        and core_user.taxes_usuario_id != taxes_user.id_usuario
    ):
        raise ValidationError(
            f"Core user {idusuario} is already linked to taxes_usuario_id="
            f"{core_user.taxes_usuario_id}."
        )
    core_user.taxes_usuario_id = taxes_user.id_usuario
    core_user.negocio_id = taxes_user.negocio_id
    core_user.save(update_fields=["taxes_usuario_id", "negocio_id"])
    return core_user


def create_taxes_usuario(
    *,
    actor,
    usuario: str,
    persona: dict,
    email: str = "",
    telefono: str = "",
    negocio_id: int | None = None,
    rol_id: int = DEFAULT_ROL_ID,
    estado: int = DEFAULT_ESTADO,
    clave: str = "",
    idusuario: int | None = None,
) -> dict:
    usuario = _blank(usuario)
    if not usuario:
        raise ValidationError({"usuario": "This field is required."})
    if len(usuario) > 20:
        raise ValidationError({"usuario": "Ensure this field has no more than 20 characters."})

    resolved_negocio_id = negocio_id or getattr(actor, "negocio_id", None)
    if not resolved_negocio_id:
        raise ValidationError(
            {"negocio_id": "Required (or set negocio_id on the authenticated user)."}
        )

    with transaction.atomic(using=POSTGRES_DB):
        if Usuarios.objects.using(POSTGRES_DB).filter(usuario=usuario).exists():
            raise ValidationError({"usuario": f"'{usuario}' already exists."})

        persona_row = _create_persona(persona)
        taxes_clave = clave or ""
        taxes_user = Usuarios.objects.using(POSTGRES_DB).create(
            id_usuario=next_serial_id("usuarios", "id_usuario"),
            usuario=usuario,
            clave=taxes_clave,
            foto="",
            telefono=_blank(telefono),
            email=_blank(email) or _blank(persona_row.email),
            clave_encriptada=taxes_clave,
            estado=estado,
            persona_id=persona_row.id_persona,
            rol_id=rol_id,
            negocio_id=resolved_negocio_id,
        )

    core_user = None
    if idusuario is not None:
        core_user = _link_core_user(idusuario=idusuario, taxes_user=taxes_user)

    return {
        "persona": persona_row,
        "usuario": taxes_user,
        "core_user": core_user,
    }
