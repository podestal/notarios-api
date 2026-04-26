import os
import re
from typing import IO

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


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


def get_r2_bucket() -> str:
	bucket = os.environ.get("CLOUDFLARE_R2_BUCKET")
	if not bucket:
		raise RuntimeError("CLOUDFLARE_R2_BUCKET is not set")
	return bucket


# ---------------------------------------------------------------------------
# Folder defaults (override via env; any code can still pass a custom folder)
# ---------------------------------------------------------------------------

def default_folder_documentos() -> str:
	"""Default R2 path segment for generated documents (env: CLOUDFLARE_R2_FOLDER_DOCUMENTOS)."""
	return (os.environ.get("CLOUDFLARE_R2_FOLDER_DOCUMENTOS") or "documentos").strip().strip("/")


def default_folder_plantillas() -> str:
	"""Default R2 path segment for templates (env: CLOUDFLARE_R2_FOLDER_PLANTILLAS)."""
	return (os.environ.get("CLOUDFLARE_R2_FOLDER_PLANTILLAS") or "plantillas").strip().strip("/")


def validate_folder_path(folder: str) -> str:
	"""
	Normalize folder to a safe relative path (no '..', no leading slash).
	Raises ValueError if invalid. Supports nested segments, e.g. 'plantillas/v2024'.
	"""
	if folder is None:
		raise ValueError("folder is required")
	clean = str(folder).strip().strip("/")
	if not clean:
		raise ValueError("folder must be non-empty")
	if ".." in clean:
		raise ValueError("folder must not contain '..'")
	return clean


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
	`folder` may include nested segments (e.g. 'plantillas/custom'); pass through
	validate_folder_path() if the value comes from clients.
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


def full_object_key_from_stored_relative(relative_path: str) -> str:
	"""
	Build the full R2 object key from a DB-relative path (e.g. urltemplate
	'plantillas/foo.docx' without MAIN_URL). Matches keys produced by
	build_object_key('plantillas', 'foo.docx').
	"""
	rel = (relative_path or "").strip().lstrip("/")
	if not rel:
		raise ValueError("relative_path is empty")
	main_url = os.environ.get("CLOUDFLARE_R2_MAIN_URL", "").strip().strip("/")
	if main_url:
		return f"{main_url}/{rel}"
	return rel


def object_key_for_tpl_template_row(urltemplate: str | None, filename: str | None) -> str:
	"""
	Resolve R2 key for a TplTemplate row.

	Legacy rows sometimes store urltemplate without the ``plantillas/`` prefix (or
	with a trailing slash). Only treat urltemplate as a full relative path when
	it already starts with ``{default_folder_plantillas()}/``; otherwise use
	filename, or treat urltemplate as a basename under the default plantillas folder.
	"""
	folder = default_folder_plantillas()
	fn = (filename or "").strip()
	ut = (urltemplate or "").strip().strip("/")

	if ut.startswith(f"{folder}/"):
		return full_object_key_from_stored_relative(ut)
	if fn:
		return build_object_key(folder, fn)
	if ut:
		basename = ut.split("/")[-1]
		if basename:
			return build_object_key(folder, basename)
	raise ValueError("Template has no usable urltemplate or filename")


def read_bytes_from_r2(object_key: str) -> bytes:
	"""
	Download an object from R2 into memory. Raises FileNotFoundError if missing.
	"""
	bucket = get_r2_bucket()
	s3 = get_s3_client()
	try:
		resp = s3.get_object(Bucket=bucket, Key=object_key)
	except ClientError as e:
		code = e.response.get("Error", {}).get("Code", "")
		if code in ("404", "NoSuchKey", "NotFound"):
			raise FileNotFoundError(f"Object not found in R2: {object_key}") from e
		raise
	body = resp["Body"]
	return body.read()


def upload_fileobj_to_r2(fileobj: IO[bytes], object_key: str) -> None:
	"""
	Upload a file-like object to R2 under the given object_key.
	Raises on error.
	"""
	s3 = get_s3_client()
	s3.upload_fileobj(fileobj, get_r2_bucket(), object_key)
