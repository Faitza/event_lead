"""
Configuration Django du projet EventLead.

Toutes les valeurs sensibles (cle secrete, base de donnees, cles de paiement,
identifiants Google) sont lues depuis les variables d'environnement ou un
fichier .env (voir .env.example).
"""
import sys
from decimal import Decimal
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
# Vrai pendant `python manage.py test` : la limite de requêtes et le cache de contenu sont alors coupés
# (les tests qui les vérifient les rallument eux-mêmes).
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"

env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me-eventlead")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sites",
    # Authentification Google
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    # Applications EventLead
    "accounts",
    "core",
    "events",
    "gifts",
    "ads",
    "payments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Fichiers statiques servis compressés (gzip / brotli) avec un long cache navigateur
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Limite de requêtes par visiteur (voir RATELIMIT_* plus bas) ; l'équipe connectée n'est pas limitée
    "core.ratelimit.RateLimitMiddleware",
    "core.middleware.LanguagePreferenceMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "eventlead.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "eventlead.wsgi.application"

# Base de donnees : PostgreSQL en production via DATABASE_URL,
# SQLite par defaut en developpement local.
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    # Plusieurs visiteurs en même temps : SQLite attend jusqu'à 20 s au lieu d'échouer (« database is locked »)
    DATABASES["default"].setdefault("OPTIONS", {})["timeout"] = 20
else:
    # Connexions réutilisées entre deux requêtes (PostgreSQL / MySQL) ; vérifiées avant usage
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Cache : mémoire du serveur par défaut. En production avec plusieurs processus, utiliser un cache partagé,
# par exemple la base de données : CACHE_URL=dbcache://eventlead_cache puis `python manage.py createcachetable`.
CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://eventlead")}

AUTH_USER_MODEL = "accounts.CustomUser"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
try:  # argon2 en bonus si la librairie est installee
    import argon2  # noqa: F401
except ImportError:
    PASSWORD_HASHERS = PASSWORD_HASHERS[1:]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dispatch"
LOGOUT_REDIRECT_URL = "core:landing"

# django-allauth (connexion Google uniquement, le formulaire email/mot de passe
# est gere par l'application accounts)
SITE_ID = 1
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = "username"
ACCOUNT_EMAIL_VERIFICATION = "none"
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", default="")
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APP": {"client_id": GOOGLE_CLIENT_ID, "secret": GOOGLE_CLIENT_SECRET, "key": ""},
    }
}

# Trois langues : français (défaut), anglais et créole haïtien. Les textes du code sont écrits en
# français ; les traductions vivent dans locale/<langue>/LC_MESSAGES/django.po (et .mo compilés).
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("en", "English"), ("ht", "Kreyòl ayisyen")]
LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = "Lax"
TIME_ZONE = "America/Port-au-Prince"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Medias : stockage local en developpement. Pour la production, definir
# DEFAULT_FILE_STORAGE_BACKEND (ex: storages.backends.s3.S3Storage ou
# cloudinary_storage.storage.MediaCloudinaryStorage) et installer le paquet.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {
        "BACKEND": env("DEFAULT_FILE_STORAGE_BACKEND", default="django.core.files.storage.FileSystemStorage"),
    },
    # collectstatic écrit aussi une version .gz et .br de chaque fichier : le navigateur télécharge moins
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
# Les CSS et JS portent un numéro de version (?v=...) : le navigateur peut les garder une journée
WHITENOISE_MAX_AGE = 60 * 60 * 24

# Poids des envois. Au-delà, Django refuse la requête (erreur 400) avant même de la lire en entier.
# Fichiers : chaque formulaire vérifie aussi son propre plafond (photo 12 Mo, vidéo 40 Mo, album 20 photos).
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # texte d'un formulaire (hors fichiers) : 5 Mo
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # au-delà, le fichier passe par le disque au lieu de la mémoire
DATA_UPLOAD_MAX_NUMBER_FILES = 25
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="EventLead <no-reply@eventlead.ht>")
# Un serveur d'e-mail qui ne répond pas bloque la page au plus 15 s
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
SERVER_EMAIL = env("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
# Adresses prévenues par e-mail à chaque erreur du serveur (séparées par des virgules)
ADMINS = [(email, email) for email in env.list("ADMINS", default=[])]

# ---------------------------------------------------------------------------
# Parametres metier EventLead
# ---------------------------------------------------------------------------
HTG_TO_USD_RATE = Decimal("0.0075")  # 1 HTG = 0.0075 USD (taux fixe)
VIP_ORGANIZER_PRICE_HTG = Decimal(env("VIP_ORGANIZER_PRICE_HTG", default="5000"))
PAYMENT_DEMO_MODE = env.bool("PAYMENT_DEMO_MODE", default=True)
MONCASH_DEMO_OTP = "123456"
STRIPE_PUBLIC_KEY = env("STRIPE_PUBLIC_KEY", default="")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
MONCASH_CLIENT_ID = env("MONCASH_CLIENT_ID", default="")
MONCASH_CLIENT_SECRET = env("MONCASH_CLIENT_SECRET", default="")
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID", default="")
PAYPAL_CLIENT_SECRET = env("PAYPAL_CLIENT_SECRET", default="")

GEOCODER_USER_AGENT = env("GEOCODER_USER_AGENT", default="eventlead-app")

CONTACT_EMAIL = env("CONTACT_EMAIL", default="contact@eventlead.ht")
# Adresse publique du site : sert aux liens des e-mails envoyés hors d'une page (commande send_reminders)
SITE_URL = env("SITE_URL", default="http://localhost:8000")
CONTACT_PHONE = env("CONTACT_PHONE", default="+509 3700 0000")
CONTACT_WHATSAPP = env("CONTACT_WHATSAPP", default="50937000000")
CONTACT_ADDRESS = env("CONTACT_ADDRESS", default="Petion-Ville, Port-au-Prince, Haiti")

GIFT_POLL_INTERVAL_MS = 5000

# ---------------------------------------------------------------------------
# Solidité : limites, plafonds, journal des erreurs (voir docs/solidite.md)
# ---------------------------------------------------------------------------
# 01. Limite de requêtes par visiteur (adresse IP), toutes pages confondues, par minute.
RATELIMIT_ENABLED = env.bool("RATELIMIT_ENABLED", default=not TESTING)
RATELIMIT_PER_MINUTE = env.int("RATELIMIT_PER_MINUTE", default=240)
RATELIMIT_POSTS_PER_MINUTE = env.int("RATELIMIT_POSTS_PER_MINUTE", default=40)
# Derrière un hébergeur qui transmet l'adresse du visiteur dans un en-tête (PythonAnywhere : X-Real-IP),
# indiquer ici le nom de l'en-tête au format Django, par exemple HTTP_X_REAL_IP.
REAL_IP_HEADER = env("REAL_IP_HEADER", default="")

# 02. Plafonds d'appels aux services extérieurs, par jour (tout le site confondu)
GEOCODER_DAILY_LIMIT = env.int("GEOCODER_DAILY_LIMIT", default=500)
EMAIL_DAILY_LIMIT = env.int("EMAIL_DAILY_LIMIT", default=280)

# 16. Contenu qui change rarement (catégories, défilé de l'accueil) gardé en mémoire, en secondes.
# Il est effacé dès qu'un événement, une catégorie ou une publicité est modifié.
CONTENT_CACHE_SECONDS = 0 if TESTING else env.int("CONTENT_CACHE_SECONDS", default=300)

# 18. Journal des erreurs : logs/eventlead.log (gardé sur 5 fichiers de 2 Mo) + terminal + e-mail aux ADMINS
LOG_DIR = Path(env("LOG_DIR", default=str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "line": {"format": "{asctime} {levelname} {name} : {message}", "style": "{"},
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "line", "level": "INFO"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler", "filename": str(LOG_DIR / "eventlead.log"),
            "maxBytes": 2 * 1024 * 1024, "backupCount": 5, "encoding": "utf-8", "formatter": "line",
            "level": "WARNING", "delay": True,
        },
        "mail_admins": {
            "class": "django.utils.log.AdminEmailHandler", "level": "ERROR", "filters": ["require_debug_false"],
        },
    },
    "root": {"handlers": ["console", "file"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console", "file", "mail_admins"], "level": "WARNING", "propagate": False},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "eventlead": {"handlers": ["console", "file", "mail_admins"], "level": "INFO", "propagate": False},
    },
}
if TESTING:  # les tests provoquent volontairement des erreurs : rien dans le terminal ni dans le fichier
    LOGGING["handlers"]["console"]["level"] = "CRITICAL"
    LOGGING["handlers"]["file"] = {"class": "logging.NullHandler"}

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
