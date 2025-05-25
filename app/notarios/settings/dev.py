from .base import *

DEBUG = True
ALLOWED_HOSTS.extend(filter(None, os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")))

# # Use PostgreSQL for production
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "HOST": os.environ.get("DB_HOST"),
#         "NAME": os.environ.get("DB_NAME"),
#         "USER": os.environ.get("DB_USER"),
#         "PASSWORD": os.environ.get("DB_PASS"),
#     }
# }

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
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

INTERNAL_IPS = ["127.0.0.1"]

CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
CORS_ALLOWED_ORIGINS.extend(
    filter(None, os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "").split(","))
)

CORS_ALLOW_CREDENTIALS = True