import os
import re
from typing import IO

import boto3
from botocore.client import Config


def get_s3_client():
	"""
	Create and return an S3-compatible client for Cloudflare R2 using env vars.
	"""
	return boto3.client(
		"s3",
		endpoint_url=os.environ.get("CLOUDFLARE_R2_ENDPOINT"),
		aws_access_key_id=os.environ.get("CLOUDFLARE_R2_ACCESS_KEY"),
		aws_secret_access_key=os.environ.get("CLOUDFLARE_R2_SECRET_KEY"),
		config=Config(signature_version="s3v4"),
		region_name="auto",
	)


def sanitize_copy_suffix_base(base: str) -> str:
	"""
	Remove trailing OS duplicate markers from the basename (before extension):
	- macOS / browser: optional whitespace + '(n)' at end
	- Windows: optional whitespace + '-' + short integer (e.g. '-1', ' - 2') at end

	Uses 1–3 digit Windows suffixes only so structured names like '__PODER__12-2024'
	are not truncated (4-digit years stay intact).
	"""
	if base is None:
		return ""
	base = re.sub(r"\s*\(\d+\)\s*$", "", base)
	base = re.sub(r"\s*-\s*\d{1,3}\s*$", "", base)
	return base.strip()


def sanitize_uploaded_docx_filename(filename: str) -> str:
	"""
	Given a raw uploaded filename, remove trailing '(n)' (macOS/browser) and '-n'
	(Windows) copy markers before the extension; trim the basename; keep extension.
	"""
	if not filename:
		return filename
	base, ext = os.path.splitext(filename)
	base = sanitize_copy_suffix_base(base)
	return f"{base}{ext}"


def docx_filename_from_name_template(name_template: str) -> str:
	"""
	Build a .docx filename from a nameTemplate string with copy suffix removal and trimming.
	"""
	base = sanitize_copy_suffix_base(name_template or "")
	if not base:
		raise ValueError("nameTemplate resolves to empty filename")
	return f"{base}.docx"


def build_object_key(folder: str, filename: str) -> str:
	"""
	Build an object key like '{MAIN_URL}/{folder}/{filename}' ensuring no duplicate slashes.
	"""
	main_url = os.environ.get("CLOUDFLARE_R2_MAIN_URL", "").strip().strip("/")
	folder_clean = (folder or "").strip().strip("/")
	filename_clean = filename.lstrip("/")
	if main_url and folder_clean:
		return f"{main_url}/{folder_clean}/{filename_clean}"
	if main_url:
		return f"{main_url}/{filename_clean}"
	if folder_clean:
		return f"{folder_clean}/{filename_clean}"
	return filename_clean


def upload_fileobj_to_r2(fileobj: IO[bytes], object_key: str) -> None:
	"""
	Upload a file-like object to R2 under the given object_key.
	Raises on error.
	"""
	bucket = os.environ.get("CLOUDFLARE_R2_BUCKET")
	if not bucket:
		raise RuntimeError("CLOUDFLARE_R2_BUCKET is not set")
	s3 = get_s3_client()
	s3.upload_fileobj(fileobj, bucket, object_key)

