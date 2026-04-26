import io
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import IO

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


class R2StorageBackend(DocumentStorageBackend):
    """Current production behavior backed by Cloudflare R2."""

    def read_bytes(self, object_key: str) -> bytes:
        s3 = get_s3_client()
        resp = s3.get_object(Bucket=get_r2_bucket(), Key=object_key)
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


class LocalFsStorageBackend(DocumentStorageBackend):
    """
    Local filesystem backend (Windows server target).
    Not wired yet; exposed for future Phase 2 migration.
    """

    def __init__(self, root_path: str):
        self.root = Path(root_path)

    def _abs(self, object_key: str) -> Path:
        rel = str(object_key).replace("\\", "/").lstrip("/")
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
        # Local backend URL strategy will be defined in later phase.
        raise NotImplementedError("Local open_url is not configured yet.")


def get_document_storage_backend() -> DocumentStorageBackend:
    """
    Storage backend selector.
    Phase 1 default is R2 (no behavior change).
    """
    backend = (os.environ.get("DOC_STORAGE_BACKEND") or "r2").strip().lower()
    if backend == "local":
        root = (os.environ.get("DOC_STORAGE_LOCAL_ROOT") or "").strip()
        if not root:
            raise RuntimeError("DOC_STORAGE_LOCAL_ROOT is required for local backend.")
        return LocalFsStorageBackend(root)
    return R2StorageBackend()
