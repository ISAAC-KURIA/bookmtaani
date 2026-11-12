"""
BookMtaani Django Settings
Local demo only — do not deploy publicly as-is.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-bookmtaani-hackathon-demo-2026-kisii'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'bookmtaani.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'bookmtaani.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []  # Relaxed for demo

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Nairobi'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

ADMIN_SITE_HEADER = 'BookMtaani Admin'
ADMIN_SITE_TITLE = 'BookMtaani'
ADMIN_INDEX_TITLE = 'BookMtaani Administration'

# ---------------------------------------------------------------------------
# Paystack
# Replace the placeholders below with your keys from the Paystack dashboard
# (Settings > API Keys & Webhooks), or set PAYSTACK_SECRET_KEY and
# PAYSTACK_PUBLIC_KEY as environment variables on the server.
# Use sk_test_ / pk_test_ keys while testing and sk_live_ / pk_live_ for real money.
# NEVER commit real keys to Git.
# ---------------------------------------------------------------------------
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', 'sk_test_ed46062505c410939f10e476a7413396941e3082')
# Not needed by the access-code popup flow used here (the server starts the
# transaction with the secret key). Kept for reference / future inline use.
PAYSTACK_PUBLIC_KEY = os.environ.get('PAYSTACK_PUBLIC_KEY', 'pk_test_5193a5889a9b2ff919494d438f6386901d33ecef')
PAYSTACK_CURRENCY = 'KES'
PAYSTACK_BASE_URL = 'https://api.paystack.co'
