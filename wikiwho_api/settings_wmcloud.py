# import raven

from .settings_base import *

# TODO https://docs.djangoproject.com/en/1.9/howto/deployment/checklist/

DEBUG = False
TEMPLATES[0]['OPTIONS']['debug'] = DEBUG
SERVER_LEVEL = LEVEL_PRODUCTION

ACTIONS_LOG = '/var/log/django/actions_log'
ACTIONS_MAX_WORKERS = 12
EVENTS_STREAM_LOG = '/var/log/django/events_streamer'

SWAGGER_SETTINGS['VALIDATOR_URL'] = 'https://online.swagger.io/validator'

ALLOWED_HOSTS = ['wikiwho-api.wmcloud.org', 'wikiwho.wmflabs.org']

ONLY_READ_ALLOWED = False

ACTIONS_LANGUAGES = ['tr', 'eu', 'es', 'de', 'en']
PICKLE_FOLDER_EN = '/pickles/en'
PICKLE_FOLDER_EU = '/pickles/eu'
PICKLE_FOLDER_ES = '/pickles/es'
PICKLE_FOLDER_DE = '/pickles/de'
PICKLE_FOLDER_TR = '/pickles/tr'
