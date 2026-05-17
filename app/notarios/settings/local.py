from .base import *

DEBUG = True
ALLOWED_HOSTS.extend(filter(None, os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "HOST": os.environ.get("DATABASE_HOST"),
        "NAME": os.environ.get("DATABASE_NAME"),
        "USER": os.environ.get("DATABASE_USER"),
        "PASSWORD": os.environ.get("DATABASE_PASSWORD"),
        "PORT": '3306',
    }
}

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware"]

INTERNAL_IPS = ["127.0.0.1"]

CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
CORS_ALLOWED_ORIGINS.extend(
    filter(None, os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "").split(","))
)

CORS_ALLOW_CREDENTIALS = True

# Document storage: local filesystem (override via .env DOC_STORAGE_*)
DOC_STORAGE_BACKEND = os.environ.get("DOC_STORAGE_BACKEND", "local")
DOC_STORAGE_LOCAL_ROOT = os.environ.get(
    "DOC_STORAGE_LOCAL_ROOT",
    "/Users/podestal/Documents/documentosNotariales",
)
os.environ.setdefault("DOC_STORAGE_BACKEND", DOC_STORAGE_BACKEND)
os.environ.setdefault("DOC_STORAGE_LOCAL_ROOT", DOC_STORAGE_LOCAL_ROOT)

# Add the session cookie middleware to the beginning of the middleware list
MIDDLEWARE = ['sisgen.middleware.SessionCookieMiddleware'] + MIDDLEWARE