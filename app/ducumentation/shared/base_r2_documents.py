import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.http import JsonResponse
import os

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
        return f"rodriguez-zea/documentos/{filename}"

    def _object_key_for_template(self, template_filename: str) -> str:
        return f"rodriguez-zea/plantillas/{template_filename}"

    def _document_exists_in_r2(self, filename: str) -> bool:
        s3 = get_s3_client()
        try:
            s3.head_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=self._object_key_for_document(filename))
            return True
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code')
            if code in ('404', 'NoSuchKey'):
                return False
            raise

    def json_error(self, status_code: int, message: str, extra: dict = None) -> JsonResponse:
        payload = {'status': 'error', 'message': message}
        if extra:
            payload.update(extra)
        resp = JsonResponse(payload, status=status_code)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp 