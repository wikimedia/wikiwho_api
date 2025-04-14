import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'django.contrib.sitemaps',
    'rest_framework',
    'rest_framework_swagger',
    'api',
    'base',
    'django_extensions',
    'wikiwho',
    'account_app',
    'crispy_forms',
    'django_crontab',
    'rest_framework_tracking',
    'corsheaders',
    'WhoColor',  # to collect static files
    'api_editor',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'wikiwho_api.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')]
        ,
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

WSGI_APPLICATION = 'wikiwho_api.wsgi.application'

# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Auth
# https://docs.djangoproject.com/en/1.10/ref/settings/#std:setting-LOGIN_URL
LOGIN_URL = 'account:login'  # default is '/accounts/login/'
LOGIN_REDIRECT_URL = 'account:detail'  # default is '/accounts/profile/'
LOGOUT_REDIRECT_URL = 'home'  # default is None
# AUTH_USER_MODEL = 'account_app.User'  # default is 'auth.User'

# Sessions
# When SESSION_SAVE_EVERY_REQUEST is set to True, Django will save the session to the database on every single request.
# SESSION_SAVE_EVERY_REQUEST = True

# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
LANGUAGE_CODE = 'en'
# from django.utils.translation import ugettext_lazy as _
LANGUAGES = (
    ('ar', 'Arabic'),
    ('de', 'German'),
    ('en', 'English'),
    ('es', 'Spanish'),
    ('eu', 'Basque'),
    ('fr', 'French'),
    ('hu', 'Hungarian'),
    ('id', 'Indonesian'),
    ('it', 'Italian'),
    ('ja', 'Japanese'),
    ('nl', 'Dutch'),
    ('pl', 'Polish'),
    ('pt', 'Portuguese'),
    ('tr', 'Turkish'),
)
# LOCALE_PATHS = (
#     os.path.join(BASE_DIR, 'locale').replace('\\', '/'),
# )

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static').replace('\\', '/')
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, "assets"),
    # '/var/www/static/',
)

# MEDIA_ROOT = os.path.join(BASE_DIR, 'media').replace('\\', '/')
# MEDIA_URL = '/media/'

# CACHE
def make_key(key, key_prefix, version):
    return ':'.join([key_prefix, str(version), key])

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': 'localhost:11211',
    #     'LOCATION': 'unix:/tmp/memcached.sock',
    # One excellent feature of Memcached is its ability to share a cache over multiple servers. This means you can run
    # Memcached daemons on multiple machines, and the program will treat the group of machines as a single cache,
    # without the need to duplicate cache values on each machine.
    #     'LOCATION': [
    #         '172.19.26.240:11211',
    #         '172.19.26.242:11211',
    #     ]
    #     'TIMEOUT': None,  # default is 300 in seconds
        'TIMEOUT': 300,
        'KEY_PREFIX': '',
        'VERSION': '',
        'KEY_FUNCTION': 'wikiwho_api.settings_base.make_key',
    }
}

# REST_FRAMEWORK and Swagger UI
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'anon': '2000/day',
        # 'user': '2000/day',
        'burst': '60/minute'
    },
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.URLPathVersioning',
    # 'DEFAULT_AUTHENTICATION_CLASSES': (
    #     'rest_framework.authentication.BasicAuthentication',
    # ),
    'OVERRIDE_THROTTLE_RATES': {
        #'ulloaro': '10000/sec',
        #'xtools_user': '10000/sec',
        'XTools': '10000/sec',
        'WhoWroteThat': '3000/minute',
    },
}

SWAGGER_SETTINGS = {
    'LOGIN_URL': 'account:login',
    'LOGOUT_URL': 'account:logout',
    'USE_SESSION_AUTH': True,
    'SECURITY_DEFINITIONS': {
        'basic': {
            'type': 'basic'  # The security definitions configures which authentication methods can be used by Swagger.
            # The schemes types currently supported by the OpenAPI 2.0 spec are basic, apiKey and oauth2.
            # For more information on available options, please consult the OpenAPI Security Object Definition.
        }
    },
    'OPERATIONS_SORTER': 'alpha',  # or 'method'
    'APIS_SORTER': 'alpha',
    'DOC_EXPANSION': 'list',
    # 'JSON_EDITOR': True,
    # 'SHOW_REQUEST_HEADERS': True,
    # 'SUPPORTED_SUBMIT_METHODS': ['get', 'post', 'put', 'delete', 'patch'],
    # 'VALIDATOR_URL': 'https://online.swagger.io/validator/',
}

# REST_FRAMEWORK_EXTENSIONS = {
#     'DEFAULT_CACHE_ERRORS': False
# }

ACTIONS_LANGUAGES = ['ar', 'de', 'en', 'es', 'eu', 'fr', 'hu', 'id', 'it', 'ja', 'nl', 'pl', 'pt', 'tr']
CRONJOBS = [
    ('0 1 3 * *', 'api_editor.cron.update_actions_tables', f'>> /dev/null 2>> /var/log/django/crontab.log')
]

# where pickles are saved
PICKLE_FOLDER = 'pickles_api'
PICKLE_OPEN_TIMEOUT = 180  # 3 mins

LOG_PARSING_PATTERN = '#######*******#######'
REVISION_COUNT_CACHE_LIMIT = 100
DELETED_CONTENT_THRESHOLD_LIMIT = 5
ALL_CONTENT_THRESHOLD_LIMIT = 0
ONLY_READ_ALLOWED = False

# Wikipedia
WP_SERVER = "{}.wikipedia.org"  # changes according to language
WP_API_URL = 'https://{}/w/api.php'.format(WP_SERVER)
WP_REQUEST_TIMEOUT = 30  # [seconds]
# WP_HEADERS_USER_AGENT = 'wikiwho-api'
WP_HEADERS_USER_AGENT = 'Wikiwho API'
WP_HEADERS_FROM = 'sage@wikiedu.org'
WP_HEADERS = {'User-Agent': WP_HEADERS_USER_AGENT, 'From': WP_HEADERS_FROM}
WP_HEADERS_EXTENDED = {'User-Agent': WP_HEADERS_USER_AGENT, 'From': WP_HEADERS_FROM, "Accept": "*/*", "Host": WP_SERVER}

# registration
ACCOUNT_ACTIVATION_DAYS = 7
REGISTRATION_SALT = 'ww_registration'
DEFAULT_FROM_EMAIL = ''  # TODO

SITE_ID = 1

# Admins
ADMINS = [('Kenan', 'kenan.erdogan@gesis.org'), ('WikiWho', 'wikiwho@gesis.org')]
MANAGERS = [('Kenan', 'kenan.erdogan@gesis.org'), ('WikiWho', 'wikiwho@gesis.org')]

CRISPY_TEMPLATE_PACK = 'bootstrap3'  # http://getbootstrap.com/docs/3.3/getting-started/

# Testing
TESTING = False  # in testing mode is False by default

# Enable any Cross-domain (CORS) requests from all origins
CORS_ORIGIN_ALLOW_ALL = True
# Enable Cross-domain (CORS) GET requests from wikipedia
# CORS_ORIGIN_WHITELIST = (
#     'en.wikipedia.org'
# )
# CORS_ALLOW_METHODS = (
#     'GET',
# )

LEVEL_LOCAL = 0
LEVEL_STAGING = 1
LEVEL_PRODUCTION = 2

SERVER_LEVEL = LEVEL_LOCAL

CHOBS_CONTEXT = 5
CHOBS_LANGUAGES = ('de')

# Overridden in settings_wmcloud.py, should probably be removed from here (?)
EVENT_STREAM_WIKIS = ['dewiki', 'enwiki', 'eswiki', 'euwiki', 'frwiki', 'huwiki', 'itwiki', 'trwiki']
