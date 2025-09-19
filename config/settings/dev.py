import os
from .base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# SECURITY WARNING: keep the secret key used in production secret!
# In development, you can use a hardcoded key or get from environment
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-0yn3d*!-w@svmlc%5o^mf&fd0gyux920^jco+9!1$3zrk755ts')

# Development hosts
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '.localhost',  # Allow all subdomains of localhost
    '*.ttek.com',  # Allow all subdomains of ttek.com
    '.ttek.com',   # Allow all subdomains of ttek.com
    'tia.ttek.com',  # Specific subdomain
    'tia.edu.gh'
]

# CSRF Configuration for development
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

# Session cookie settings for development
SESSION_COOKIE_SECURE = False

# Email backend for development (console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Development-specific logging (optional)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}