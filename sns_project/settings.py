"""
sns_project の設定。

- ローカル: 環境変数なしで `python manage.py runserver` がそのまま動く
  （DEBUG=True / SQLite / 画像はローカルの media/ / メールはコンソール出力）
- Render: 環境変数 RENDER が自動で設定されるので本番モードになる
  （DEBUG=False / DATABASE_URL の Postgres / S3 / Gmail SMTP）
"""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes")


# Render上で動いているか（Renderが自動で RENDER=true を設定する）
IS_RENDER = "RENDER" in os.environ

# ---------------------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------------------
DEBUG = env_bool("DEBUG", default=not IS_RENDER)

if DEBUG:
    SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-local-dev-only")
else:
    # 本番で SECRET_KEY が無ければ起動させない
    SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
if DEBUG:
    ALLOWED_HOSTS += ["localhost", "127.0.0.1", "[::1]"]

CSRF_TRUSTED_ORIGINS = ["https://*.onrender.com"]

ROOT_URLCONF = "sns_project.urls"
WSGI_APPLICATION = "sns_project.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "storages",
    "core",
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
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# DB（本番は DATABASE_URL / ローカルは SQLite）
# ---------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# ---------------------------------------------------------------------------
# 認証
# ---------------------------------------------------------------------------
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# 静的ファイル / アップロード画像
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# アップロード上限（画像5MB + フォーム分の余裕）
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
USE_S3 = bool(AWS_STORAGE_BUCKET_NAME)

if USE_S3:
    AWS_ACCESS_KEY_ID = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
    AWS_S3_REGION_NAME = "ap-northeast-1"
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    DEFAULT_STORAGE_BACKEND = "storages.backends.s3boto3.S3Boto3Storage"
else:
    DEFAULT_STORAGE_BACKEND = "django.core.files.storage.FileSystemStorage"

STORAGES = {
    "default": {"BACKEND": DEFAULT_STORAGE_BACKEND},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

# ---------------------------------------------------------------------------
# メール（管理者への通知）
# ---------------------------------------------------------------------------
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
if EMAIL_HOST_USER:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_TIMEOUT = 10
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
else:
    # ローカルではメールを送らず、ターミナルに表示する
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = "noreply@localhost"

# 空なら通知しない
ADMIN_NOTIFY_EMAIL = os.environ.get("ADMIN_NOTIFY_EMAIL", "")

# ---------------------------------------------------------------------------
# レート制限（django-ratelimit）
# ---------------------------------------------------------------------------
# Render はリバースプロキシ経由なので REMOTE_ADDR はプロキシのIPになる。
# X-Forwarded-For の先頭をクライアントIPとして使う（core/utils.py 参照）。
# ※先頭はクライアントが偽装できるため、ログインはIPに加えてユーザー名単位でも制限している。
RATELIMIT_IP_META_KEY = "core.utils.get_client_ip"

# ---------------------------------------------------------------------------
# セキュリティ（本番のみ）
# ---------------------------------------------------------------------------
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_REFERRER_POLICY = "same-origin"
