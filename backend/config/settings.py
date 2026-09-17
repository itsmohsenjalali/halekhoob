import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or "pytest" in __import__("sys").modules or "test" in __import__("sys").argv:
        SECRET_KEY = "local-development-only-never-use-on-the-internet"
    else:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY or DJANGO_DEBUG=1 for local development.")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
CSRF_TRUSTED_ORIGINS = list(
    filter(None, os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(","))
)
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "library",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "library.middleware.PrivateCacheMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "library.context.archive_context",
            ]
        },
    }
]
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
MEDIA_ROOT = DATA_DIR / "media"
MEDIA_BACKEND = os.environ.get("MEDIA_BACKEND", "local")
if MEDIA_BACKEND not in {"local", "r2"}:
    raise ImproperlyConfigured("MEDIA_BACKEND must be local or r2.")
PUBLIC_URL = os.environ.get("APP_PUBLIC_URL", "")
public_origin = urlsplit(PUBLIC_URL)
LOOPBACK_HTTP = False
if PUBLIC_URL:
    if (
        public_origin.scheme not in {"http", "https"}
        or not public_origin.hostname
        or public_origin.username
        or public_origin.password
        or public_origin.path not in {"", "/"}
        or public_origin.query
        or public_origin.fragment
    ):
        raise ImproperlyConfigured("APP_PUBLIC_URL must be an HTTP(S) origin.")
    LOOPBACK_HTTP = public_origin.scheme == "http" and public_origin.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if not DEBUG and public_origin.scheme != "https" and not LOOPBACK_HTTP:
        raise ImproperlyConfigured("Production HTTP is allowed only through a loopback SSH tunnel.")
    ALLOWED_HOSTS.append(public_origin.hostname)
    CSRF_TRUSTED_ORIGINS.append(PUBLIC_URL.rstrip("/"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_ROOT.mkdir(exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "archive.sqlite3",
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    }
}
if os.environ.get("DATABASE_URL"):
    internal_database = os.environ.get("DATABASE_DOCKER_INTERNAL") == "1"
    database_origin = urlsplit(os.environ["DATABASE_URL"])
    if internal_database and database_origin.hostname != "db":
        raise ImproperlyConfigured(
            "DATABASE_DOCKER_INTERNAL is only for the private Docker db service."
        )
    DATABASES["default"] = dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=0,
        conn_health_checks=True,
        ssl_require=not DEBUG and not internal_database,
    )
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured("DATABASE_URL must use PostgreSQL.")
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
    DATABASES["default"].setdefault("OPTIONS", {})["connect_timeout"] = 10
    if internal_database:
        DATABASES["default"]["OPTIONS"]["sslmode"] = "disable"
R2_ENDPOINT_URL = os.environ.get("R2_ENDPOINT_URL", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_PREFIX = os.environ.get("R2_PREFIX", "archive").strip("/")
R2_URL_TTL = int(os.environ.get("R2_URL_TTL", "3600"))
if MEDIA_BACKEND == "r2":
    if not re.fullmatch(
        r"https://[a-f0-9]{32}(?:\.eu|\.fedramp)?\.r2\.cloudflarestorage\.com", R2_ENDPOINT_URL
    ):
        raise ImproperlyConfigured("Use the HTTPS S3 API endpoint from the R2 dashboard.")
    if not all([R2_BUCKET_NAME, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
        raise ImproperlyConfigured("Set R2 bucket and scoped S3 API credentials.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", R2_PREFIX):
        raise ImproperlyConfigured("R2_PREFIX must be one nonempty path segment.")
    if not 300 <= R2_URL_TTL <= 86400:
        raise ImproperlyConfigured("R2_URL_TTL must be between 300 and 86400 seconds.")
    if not DEBUG and not os.environ.get("DATABASE_URL"):
        raise ImproperlyConfigured("Production R2 requires PostgreSQL.")
WORKER_LEASE_SECONDS = 120
R2_DELETE_DELAY_DAYS = max(1, int(os.environ.get("R2_DELETE_DELAY_DAYS", "7")))
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "fa"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static", ("theme", BASE_DIR / "theme")]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = "halekhoob_sessionid"
CSRF_COOKIE_NAME = "halekhoob_csrftoken"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_SECURE = not DEBUG and not LOOPBACK_HTTP
CSRF_COOKIE_SECURE = not DEBUG and not LOOPBACK_HTTP
SECURE_SSL_REDIRECT = not DEBUG and not LOOPBACK_HTTP
SECURE_SSL_HOST = public_origin.netloc if PUBLIC_URL and public_origin.scheme == "https" else None
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SECURE_HSTS_SECONDS = 31536000 if not DEBUG and not LOOPBACK_HTTP else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
ARCHIVE_MAX_BYTES = int(os.environ.get("ARCHIVE_MAX_BYTES", 100_000_000_000))
MIN_FREE_BYTES = int(os.environ.get("MIN_FREE_BYTES", 2_000_000_000))
DOWNLOAD_TIMEOUT = int(os.environ.get("DOWNLOAD_TIMEOUT", 1800))
YOUTUBE_COOKIES_FILE = os.environ.get("YOUTUBE_COOKIES_FILE", "")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Clerk is the only production login provider. Legacy forms are local test tools only.
LEGACY_UI_ENABLED = DEBUG and os.environ.get("LEGACY_UI_ENABLED") == "1"
CLERK_ISSUER = os.environ.get("CLERK_ISSUER", "").rstrip("/")
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")
CLERK_AUTHORIZED_PARTIES = list(filter(None, os.environ.get("CLERK_AUTHORIZED_PARTIES", PUBLIC_URL).split(",")))
CLERK_LEGACY_OWNER_EMAIL = os.environ.get("CLERK_LEGACY_OWNER_EMAIL", "").strip().lower()
DEFAULT_USER_STORAGE_BYTES = int(os.environ.get("DEFAULT_USER_STORAGE_BYTES", "1000000000"))
DOWNLOAD_URL_TTL = 300

HOST_METRICS_FILE = os.environ.get("HOST_METRICS_FILE", "")
