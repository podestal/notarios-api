import io
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import IO, Optional

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

from .storage import (
    get_r2_bucket,
    get_s3_client,
)


class DocumentStorageBackend(ABC):
    """
    Single storage interface for document/template persistence.
    Phase 1: R2 remains default behavior.
    """

    @abstractmethod
    def read_bytes(self, object_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def write_bytes(self, object_key: str, data: bytes) -> None:
        raise NotImplementedError

    @abstractmethod
    def upload_fileobj(self, object_key: str, fileobj: IO[bytes]) -> None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def open_url(self, object_key: str, expires_in: int = 3600) -> str:
        raise NotImplementedError

    @abstractmethod
    def delete(self, object_key: str) -> None:
        raise NotImplementedError


class R2StorageBackend(DocumentStorageBackend):
    """Current production behavior backed by Cloudflare R2."""

    def read_bytes(self, object_key: str) -> bytes:
        s3 = get_s3_client()
        try:
            resp = s3.get_object(Bucket=get_r2_bucket(), Key=object_key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(f"Object not found: {object_key}") from e
            raise
        return resp["Body"].read()

    def write_bytes(self, object_key: str, data: bytes) -> None:
        self.upload_fileobj(object_key, io.BytesIO(data))

    def upload_fileobj(self, object_key: str, fileobj: IO[bytes]) -> None:
        s3 = get_s3_client()
        s3.upload_fileobj(fileobj, get_r2_bucket(), object_key)

    def exists(self, object_key: str) -> bool:
        s3 = get_s3_client()
        try:
            s3.head_object(Bucket=get_r2_bucket(), Key=object_key)
            return True
        except Exception:
            return False

    def open_url(self, object_key: str, expires_in: int = 3600) -> str:
        s3 = get_s3_client()
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": get_r2_bucket(), "Key": object_key},
            ExpiresIn=expires_in,
        )

    def delete(self, object_key: str) -> None:
        s3 = get_s3_client()
        s3.delete_object(Bucket=get_r2_bucket(), Key=object_key)


class LocalFsStorageBackend(DocumentStorageBackend):
    """
    Local filesystem backend (Windows server target).
    Not wired yet; exposed for future Phase 2 migration.
    """

    def __init__(self, root_path: str):
        self.root = Path(root_path)

    def _abs(self, object_key: str) -> Path:
        rel = str(object_key).replace("\\", "/").lstrip("/")
        main_url = (os.environ.get("CLOUDFLARE_R2_MAIN_URL") or "").strip().strip("/")
        if main_url and rel.startswith(f"{main_url}/"):
            rel = rel[len(main_url) + 1 :]
        return self.root / rel

    def read_bytes(self, object_key: str) -> bytes:
        return self._abs(object_key).read_bytes()

    def write_bytes(self, object_key: str, data: bytes) -> None:
        path = self._abs(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def upload_fileobj(self, object_key: str, fileobj: IO[bytes]) -> None:
        path = self._abs(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(fileobj.read())

    def exists(self, object_key: str) -> bool:
        return self._abs(object_key).exists()

    def open_url(self, object_key: str, expires_in: int = 3600) -> str:
        # Local backend does not provide open/presigned URLs.
        # Keep endpoints stable by returning empty URL; callers should use mode=download.
        return ""

    def delete(self, object_key: str) -> None:
        path = self._abs(object_key)
        if path.is_file():
            path.unlink()


_backend_instance: Optional[DocumentStorageBackend] = None


def get_document_storage_backend() -> DocumentStorageBackend:
    """
    Storage backend selector.
    Phase 1 default is R2 (no behavior change).
    """
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    raw_backend = os.environ.get("DOC_STORAGE_BACKEND")
    backend = (raw_backend or "r2").strip().lower()

    if backend == "local":
        root = (os.environ.get("DOC_STORAGE_LOCAL_ROOT") or "C:/documentos/gc").strip()
        _backend_instance = LocalFsStorageBackend(root)
        logger.info(
            "Document storage: LOCAL filesystem (DOC_STORAGE_BACKEND=local, root=%s)",
            root,
        )
        return _backend_instance

    if backend != "r2":
        logger.warning(
            "Unknown DOC_STORAGE_BACKEND=%r; falling back to Cloudflare R2",
            raw_backend,
        )

    bucket = get_r2_bucket()
    prefix = (os.environ.get("CLOUDFLARE_R2_MAIN_URL") or "").strip() or "(none)"
    _backend_instance = R2StorageBackend()
    logger.info(
        "Document storage: Cloudflare R2 (DOC_STORAGE_BACKEND=%s, bucket=%s, prefix=%s)",
        raw_backend or "(unset, default r2)",
        bucket,
        prefix,
    )
    return _backend_instance


def proyecto_document_filename(kardex: str) -> str:
    return f"__PROY__{kardex}.docx"


def proyecto_document_object_key(kardex: str) -> str:
    """Object key for protocolares project docs (matches TemplateManager paths)."""
    prefix = (os.environ.get("CLOUDFLARE_R2_MAIN_URL") or "").strip().strip("/")
    filename = proyecto_document_filename(kardex)
    if prefix:
        return f"{prefix}/documentos/{filename}"
    return f"documentos/{filename}"


def read_proyecto_document_bytes(kardex: str) -> Optional[bytes]:
    """Read __PROY__{kardex}.docx from the configured storage backend, or None if missing."""
    backend = get_document_storage_backend()
    object_key = proyecto_document_object_key(kardex)
    if not backend.exists(object_key):
        return None
    try:
        return backend.read_bytes(object_key)
    except FileNotFoundError:
        return None


def read_tpl_template_bytes(template_id: int) -> bytes:
    """Read a TplTemplate .docx from the configured storage backend (local or R2)."""
    from notaria.models import TplTemplate

    from .storage import object_key_for_tpl_template_row

    tpl = TplTemplate.objects.get(pktemplate=template_id)
    object_key = object_key_for_tpl_template_row(tpl.urltemplate, tpl.filename)
    try:
        return get_document_storage_backend().read_bytes(object_key)
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Template not found: {object_key}") from e


def proyecto_document_open_url(kardex: str, expires_in: int = 3600) -> str:
    """
    URL for opening a project document in Word.
    R2: presigned URL. Local: empty (caller should use the Django download route).
    """
    backend = get_document_storage_backend()
    return backend.open_url(proyecto_document_object_key(kardex), expires_in=expires_in)
