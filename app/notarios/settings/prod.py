from .base import *

# Add the session cookie middleware to the beginning of the middleware list
MIDDLEWARE = ['sisgen.middleware.SessionCookieMiddleware'] + MIDDLEWARE

DEBUG = True
ALLOWED_HOSTS.extend(filter(None, os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")))

from .databases import build_databases, postgres_enabled

DATABASES = build_databases()

if postgres_enabled():
    DATABASE_ROUTERS = ["notarios.db_router.PostgresRouter"]

MIDDLEWARE += ["whitenoise.middleware.WhiteNoiseMiddleware"]

CORS_ALLOWED_ORIGINS = []
raw_cors_origins = os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "")
print(f"DEBUG: Raw CORS origins from env: '{raw_cors_origins}'")

cors_origins = [url.strip() for url in raw_cors_origins.split(",") if url.strip()]
print(f"DEBUG: Processed CORS origins: {cors_origins}")

if cors_origins:
    CORS_ALLOWED_ORIGINS.extend(cors_origins)
    print(f"DEBUG: Final CORS_ALLOWED_ORIGINS: {CORS_ALLOWED_ORIGINS}")
else:
    # Fallback for testing - allow all origins
    CORS_ALLOW_ALL_ORIGINS = True
    print("DEBUG: No CORS origins found, allowing all origins")

CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = []
CSRF_TRUSTED_ORIGINS.extend(
    [url.strip() for url in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if url.strip()]
)