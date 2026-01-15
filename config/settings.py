import os
import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Security
DEBUG = os.getenv('DEBUG', '0') == '1'
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-key-for-local-development-only-do-not-use-in-production'
    else:
        raise ValueError(
            'SECRET_KEY environment variable is required in production. '
            'Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
        )

# Parse ALLOWED_HOSTS from env (comma-separated)
# In production, must explicitly set ALLOWED_HOSTS (no wildcard default)
if DEBUG:
    ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0,*').split(',')
else:
    _allowed_hosts = os.getenv('ALLOWED_HOSTS', '')
    if not _allowed_hosts:
        raise ValueError(
            'ALLOWED_HOSTS environment variable is required in production. '
            'Example: ALLOWED_HOSTS=.ttek-sms.com,your-server-ip'
        )
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(',')]

# CSRF Trusted Origins for PaaS deployments (Railway, Render, Fly.io)
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()
]

# Platform detection for proxy header configuration
RAILWAY = os.getenv('RAILWAY_ENVIRONMENT', '') != ''
RENDER = os.getenv('RENDER', 'false').lower() == 'true'
FLY = os.getenv('FLY_APP_NAME', '') != ''

# Trust proxy headers (required for HTTPS redirect to work correctly behind nginx/proxy)
# Enable for all production environments (PaaS or self-hosted behind nginx)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# --- 2. APPS ---
SHARED_APPS = (
    'django_tenants',
    'schools',
    'accounts',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_celery_beat',

    #Third_party Apps
    'django_htmx',
    'tailwind',
    'theme',
    'storages',  # django-storages for handling file storage
)

TENANT_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    #Local Apps
    'core',
    'academics',
    'students',
    'teachers',
    'communications',
    'accounts',
    'gradebook',
    'finance',

)

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

if DEBUG:
    INSTALLED_APPS += ["django_browser_reload"]

TENANT_MODEL = "schools.School"
TENANT_DOMAIN_MODEL = "schools.Domain"

# --- 3. MIDDLEWARE ---
MIDDLEWARE = [
    'core.middleware.HealthCheckMiddleware',  # Must be before TenantNotFoundMiddleware
    'core.middleware.TenantNotFoundMiddleware',  # Custom middleware for friendly error page
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.middleware.ForcePasswordChangeMiddleware',
    'accounts.middleware.ProfileSetupMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

if DEBUG:
    # Add django_browser_reload middleware only in DEBUG mode
    MIDDLEWARE += [
        "django_browser_reload.middleware.BrowserReloadMiddleware",
    ]

# --- 1. DATABASE (Multi-Tenant) ---
if DEBUG:
    # DEVELOPMENT DATABASE SETTINGS
    DATABASES = {
        'default': dj_database_url.config(
            default=os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/ttek_sms_db'),
            engine='django_tenants.postgresql_backend',
            conn_max_age=0,  # No connection pooling in dev for easier debugging
            conn_health_checks=False,  # Disabled for faster local development
        )
    }
    # Optional: Add additional dev-specific database options
    DATABASES['default'].update({
        'ATOMIC_REQUESTS': True,  # Wrap each request in a transaction
        'OPTIONS': {
            'connect_timeout': 10,
        }
    })
else:
    # PRODUCTION DATABASE SETTINGS
    DATABASES = {
        'default': dj_database_url.config(
            default=os.getenv('DATABASE_URL'),
            engine='django_tenants.postgresql_backend',
            conn_max_age=600,  # Connection pooling - reuse connections for 10 minutes
            conn_health_checks=True,  # Enable health checks
            ssl_require=True,  # Require SSL in production
        )
    }
    # Production-specific database options
    DATABASES['default'].update({
        'ATOMIC_REQUESTS': True,
        'DISABLE_SERVER_SIDE_CURSORS': True,  # Better for connection pooling
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000',  # 30 second query timeout
            'sslmode': os.getenv('DB_SSLMODE', 'disable'),  # SSL mode (disable for Docker, require for external DB)
        }
    })

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

AUTH_USER_MODEL = 'accounts.User'

TAILWIND_APP_NAME = 'theme'

PUBLIC_SCHEMA_NAME = 'public'  # Schema name for the public tenant
PUBLIC_SCHEMA_URLCONF = 'config.urls_public'
ROOT_URLCONF = 'config.urls'
SHOW_PUBLIC_IF_NO_TENANT_FOUND = False  # Custom middleware handles this with a friendly error page

# Domains that show the public landing page (subdomains will show "School Not Found" if not registered)
# Can be set via environment variable as comma-separated list: PUBLIC_DOMAINS=example.com,www.example.com
PUBLIC_DOMAINS = [d.strip() for d in os.getenv('PUBLIC_DOMAINS', 'ttek-sms.com,www.ttek-sms.com,localhost,127.0.0.1').split(',')]

# Show public landing page on main domain
# Set SHOW_PUBLIC_LANDING=False in .env to show "Access Your School" page instead
SHOW_PUBLIC_LANDING = os.getenv('SHOW_PUBLIC_LANDING', 'True').lower() in ('true', '1', 'yes')

# --- 4. TEMPLATES ---
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.school_branding',
                'core.context_processors.academic_session',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- 5. SECURITY (Production) ---
# Multi-tenant session isolation: Each subdomain gets its own session cookie
# This prevents sessions from being shared across tenants (subdomains)
SESSION_COOKIE_DOMAIN = None  # Use exact subdomain, not shared across *.ttek-sms.com
CSRF_COOKIE_DOMAIN = None     # Same for CSRF

# SameSite cookie attribute - protects against CSRF attacks
SESSION_COOKIE_SAMESITE = 'Lax'  # Allows top-level navigations
CSRF_COOKIE_SAMESITE = 'Lax'

if not DEBUG:
    # SSL redirect - set SECURE_SSL_REDIRECT=True after SSL certificates are configured
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() == 'true'

    # Always secure cookies in production (even before SSL redirect is enabled)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Security headers
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

    # HSTS - only enable after SSL is fully working
    if SECURE_SSL_REDIRECT:
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
    else:
        import warnings
        warnings.warn(
            'SECURE_SSL_REDIRECT is disabled. Enable after SSL setup: SECURE_SSL_REDIRECT=True',
            RuntimeWarning
        )

# --- 6. COMMUNICATION ---
# Email - Tenant-aware backend that uses per-school SMTP settings when configured
# Falls back to global settings (DEFAULT_EMAIL_BACKEND) when school email is disabled
EMAIL_BACKEND = 'core.email_backend.TenantEmailBackend'
DEFAULT_EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@schoolos.com')

# SMS & Payment Configuration
# NOTE: These are configured PER-SCHOOL in the admin dashboard (Settings → SMS/Payment)
# Each school chooses their own provider and enters their own API keys.
# Supported SMS providers: Arkesel, Hubtel, Africa's Talking
# Supported Payment providers: Paystack, Hubtel, Flutterwave

# Field encryption key (store securely, different from gateway keys)
# Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY')
if not FIELD_ENCRYPTION_KEY:
    if DEBUG:
        # Development-only default key - DO NOT use in production
        # This is a valid Fernet key for local development only
        FIELD_ENCRYPTION_KEY = 'S-lCiLx0ym9wfNDS2JegDCDqzjocWksm_GLceVEMMWQ='
    else:
        raise ValueError(
            'FIELD_ENCRYPTION_KEY environment variable is required in production. '
            'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )

# Optional: Platform-level default credentials (for schools that haven't set up their own)
PLATFORM_PAYSTACK_SECRET_KEY = os.getenv('PLATFORM_PAYSTACK_SECRET_KEY', default='')
PLATFORM_PAYSTACK_PUBLIC_KEY = os.getenv('PLATFORM_PAYSTACK_PUBLIC_KEY', default='')

# --- 7. CELERY ---
CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('REDIS_URL', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes

# --- 7.1 CACHING ---
# Use Redis for caching to ensure cache is shared across workers and Celery
# Use database 1 for cache (database 0 is used by Celery)
REDIS_CACHE_URL = os.getenv('REDIS_CACHE_URL', os.getenv('REDIS_URL', 'redis://redis:6379/0')).replace('/0', '/1')

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_CACHE_URL,
        'KEY_PREFIX': 'ttek',
        'OPTIONS': {
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
        }
    }
}

# Session storage - use cache for better performance
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# --- 8. STATIC FILES ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []

STORAGES = {
    "default": {
        "BACKEND": 'core.storage.CustomSchemaStorage',
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# 5. AUTH
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:index'
LOGOUT_REDIRECT_URL = '/admin/login/'  # For admin panel logout (tenant logout uses its own next_page)

# --- 9. MEDIA FILES ---
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
MULTITENANT_RELATIVE_MEDIA_ROOT = 'schools/%s/media'

# --- 10. LOGGING ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# --- 11. AUTH ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- 12. INTERNATIONALIZATION ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# --- 13. DEFAULT PRIMARY KEY ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'