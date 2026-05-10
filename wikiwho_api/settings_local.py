from .settings_base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
TEMPLATES[0]['OPTIONS']['debug'] = DEBUG
SERVER_LEVEL = LEVEL_LOCAL
ACTIONS_LOG = '/home/wikiwho/wikiwho_api/tmp_pickles/actions_log'
ACTIONS_MAX_WORKERS = 0

EVENTS_STREAM_LOG = '/home/wikiwho/wikiwho_api/tmp_pickles/events_stream_log'

#ACTIONS_LANGUAGES = ['tr', 'eu', 'es', 'de', 'en']
ACTIONS_LANGUAGES = ['eu']
CRONJOBS = [
    ('23 * * * *', 'api_editor.cron.update_actions_tables', f'>> /tmp/cron_prints.log 2>> /tmp/cron_errors.log')
]

ALLOWED_HOSTS = ['localhost', '127.0.0.1']
INTERNAL_IPS = ['127.0.0.1']

# Pickle folder paths without ending /
# PICKLE_FOLDER = 'tmp_pickles'
PICKLE_FOLDER_EN = 'tmp_pickles/en'
PICKLE_FOLDER_EU = 'tmp_pickles/eu'
PICKLE_FOLDER_DE = 'tmp_pickles/de'
PICKLE_FOLDER_TR = 'tmp_pickles/tr'
PICKLE_FOLDER_NO = 'tmp_pickles/no'

INSTALLED_APPS += ['debug_toolbar',
                   'debug_panel']

MIDDLEWARE += ['debug_panel.middleware.DebugPanelMiddleware']

SWAGGER_SETTINGS['VALIDATOR_URL'] = 'https://online.swagger.io/validator'

# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
#     }
# }

# Default logging for Django. This sends an email to the site admins on every
# HTTP 500 error. Depending on DEBUG, all other log records are either sent to
# the console (DEBUG=True) or discarded (DEBUG=False) by means of the
# require_debug_true filter.
# https://docs.djangoproject.com/en/1.10/topics/logging/#examples

CHOBS_LANGUAGES = ('en', 'tr', 'de', 'es', 'eu')
