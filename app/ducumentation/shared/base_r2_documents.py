import io

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.http import JsonResponse
import os

from ducumentation.storage_backends import get_document_storage_backend

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
    return _s3_client


class BaseR2DocumentService:
    def _object_key_for_document(self, filename: str) -> str:
        return f"{os.environ.get('CLOUDFLARE_R2_MAIN_URL')}/documentos/{filename}"

    def _object_key_for_template(self, template_filename: str) -> str:
        return f"{os.environ.get('CLOUDFLARE_R2_MAIN_URL')}/plantillas/{template_filename}"

    def _document_exists_in_r2(self, filename: str) -> bool:
        return self._storage_backend().exists(self._object_key_for_document(filename))

    def _storage_backend(self):
        return get_document_storage_backend()

    def _read_document_bytes(self, filename: str) -> bytes:
        return self._storage_backend().read_bytes(self._object_key_for_document(filename))

    def _read_template_bytes(self, template_filename: str) -> bytes:
        return self._storage_backend().read_bytes(self._object_key_for_template(template_filename))

    def _write_document_buffer(self, buffer, filename: str) -> None:
        # Never pass the original response buffer to storage upload, because some
        # adapters/SDK paths may consume/close it. Keep original buffer intact for
        # immediate HTTP response.
        buffer.seek(0)
        payload = buffer.read()
        upload_stream = io.BytesIO(payload)
        self._storage_backend().upload_fileobj(self._object_key_for_document(filename), upload_stream)
        # Rewind the original buffer for caller response path.
        buffer.seek(0)

    def _open_document_url(self, filename: str, expires_in: int = 3600) -> str:
        return self._storage_backend().open_url(self._object_key_for_document(filename), expires_in)

    def json_error(self, status_code: int, message: str, extra: dict = None) -> JsonResponse:
        payload = {'status': 'error', 'message': message}
        if extra:
            payload.update(extra)
        resp = JsonResponse(payload, status=status_code)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp 