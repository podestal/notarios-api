import os
from pathlib import Path

from django.conf import settings

POSTGRES_DB = "postgres"


def xml_notaria_root() -> Path:
    configured = os.environ.get("XML_NOTARIA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    # BASE_DIR is app/notarios; xml_notaria lives alongside it at app/xml_notaria.
    return Path(settings.BASE_DIR).parent / "xml_notaria"


def plantillas_dir() -> Path:
    return xml_notaria_root() / "plantillas"


def generar_dir() -> Path:
    return xml_notaria_root() / "generar"


def firmar_dir() -> Path:
    return xml_notaria_root() / "firmar"


def emitir_dir() -> Path:
    return xml_notaria_root() / "emitir"


def exception_dir() -> Path:
    return xml_notaria_root() / "exception"


def comprobante_filename(*, ruc: str, codigo_comprobante: str, serie: str, numero: int) -> str:
    numero_padded = str(numero).zfill(8)
    return f"{ruc}-{codigo_comprobante}-{serie}-{numero_padded}.XML"


def generar_path(*, ruc: str, codigo_comprobante: str, serie: str, numero: int) -> Path:
    return generar_dir() / comprobante_filename(
        ruc=ruc,
        codigo_comprobante=codigo_comprobante,
        serie=serie,
        numero=numero,
    )


def firmar_path(*, ruc: str, codigo_comprobante: str, serie: str, numero: int) -> Path:
    return firmar_dir() / comprobante_filename(
        ruc=ruc,
        codigo_comprobante=codigo_comprobante,
        serie=serie,
        numero=numero,
    )


def firmar_zip_path(*, ruc: str, codigo_comprobante: str, serie: str, numero: int) -> Path:
    base = firmar_dir() / comprobante_filename(
        ruc=ruc,
        codigo_comprobante=codigo_comprobante,
        serie=serie,
        numero=numero,
    ).removesuffix(".XML")
    return base.with_suffix(".ZIP")


def cdr_path(*, archivo: str) -> Path:
    return emitir_dir() / f"R-{archivo}.XML"


def exception_path(*, archivo: str) -> Path:
    return exception_dir() / f"E-{archivo}.XML"


def ensure_output_dirs() -> None:
    generar_dir().mkdir(parents=True, exist_ok=True)
    firmar_dir().mkdir(parents=True, exist_ok=True)
    emitir_dir().mkdir(parents=True, exist_ok=True)
    exception_dir().mkdir(parents=True, exist_ok=True)
