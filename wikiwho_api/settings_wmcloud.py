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

ALLOWED_HOSTS = ['wikiwho-api.wmcloud.org', 'wikiwho.wmcloud.org', 'wikiwho-flower.wmcloud.org']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

ONLY_READ_ALLOWED = False

ACTIONS_LANGUAGES = [
    'af',
    'als',
    'ar',
    'az',
    'be',
    'bg',
    'bn',
    'ce',
    'cs',
    'cy',
    'da',
    'de',
    'dsb',
    'el',
    'en',
    'eo',
    'es',
    'et',
    'eu',
    'fa',
    'fi',
    'fr',
    'gl',
    'he',
    'hi',
    'hr',
    'hu',
    'ia',
    'id',
    'it',
    'ja',
    'ka',
    'kk',
    'lt',
    'lv',
    'mk',
    'ml',
    'ms',
    'ne',
    'nl',
    'no',
    'pl',
    'pt',
    'ro',
    'ru',
    'sh',
    'simple',
    'sk',
    'sl',
    'sq',
    'sr',
    'sv',
    'ta',
    'th',
    'tl',
    'tr',
    'uk',
    'ur',
    'uz',
    'vec',
    'vi',
    'zh',
]
EVENT_STREAM_WIKIS = [
    'alswiki',
    'arwiki',
    'bewiki',
    'bgwiki',
    'bnwiki',
    'cewiki',
    'cswiki',
    'cywiki',
    'dawiki',
    'dsbwiki',
    'dewiki',
    'elwiki',
    'enwiki',
    'eowiki',
    'eswiki',
    'etwiki',
    'euwiki',
    'fawiki',
    'fiwiki',
    'frwiki',
    'glwiki',
    'hewiki',
    'hiwiki',
    'hrwiki',
    'huwiki',
    'iawiki',
    'idwiki',
    'itwiki',
    'kawiki',
    'kkwiki',
    'ltwiki',
    'mlwiki',
    'mswiki',
    'newiki',
    'nlwiki',
    'nowiki',
    'plwiki',
    'ptwiki',
    'rowiki',
    'ruwiki',
    'shwiki',
    'simplewiki',
    'skwiki',
    'sqwiki',
    'srwiki',
    'svwiki',
    'thwiki',
    'tlwiki',
    'trwiki',
    'urwiki',
    'ukwiki',
    'uzwiki',
    'vecwiki',
    'viwiki',
]

# On pickle_storage volume, mounted to /pickles
PICKLE_FOLDER_AF = '/pickles/af'
PICKLE_FOLDER_AZ = '/pickles/az'
PICKLE_FOLDER_BG = '/pickles/bg'
PICKLE_FOLDER_CY = '/pickles/cy'
PICKLE_FOLDER_DA = '/pickles/da'
PICKLE_FOLDER_EN = '/pickles/en'
PICKLE_FOLDER_HE = '/pickles/he'
PICKLE_FOLDER_LV = '/pickles/lv'
PICKLE_FOLDER_MK = '/pickles/mk'
PICKLE_FOLDER_ML = '/pickles/ml'
PICKLE_FOLDER_NE = '/pickles/ne'
PICKLE_FOLDER_SL = '/pickles/sl'
PICKLE_FOLDER_TA = '/pickles/ta'
PICKLE_FOLDER_TH = '/pickles/th'
PICKLE_FOLDER_TL = '/pickles/tl'
PICKLE_FOLDER_UR = '/pickles/ur'

# On pickle_storage02 volume, mounted to /pickles-02
PICKLE_FOLDER_AR = '/pickles-02/ar'
PICKLE_FOLDER_ES = '/pickles-02/es' # Moved from /pickles/es @ 2026-02-09, T407660
PICKLE_FOLDER_EU = '/pickles-02/eu' # Moved from /pickles/eu @ 2026-02-09, T407660
PICKLE_FOLDER_FR = '/pickles-02/fr'
PICKLE_FOLDER_GL = '/pickles-02/gl'
PICKLE_FOLDER_HR = '/pickles-02/hr'
PICKLE_FOLDER_HU = '/pickles-02/hu'
PICKLE_FOLDER_ID = '/pickles-02/id'
PICKLE_FOLDER_IT = '/pickles-02/it'
PICKLE_FOLDER_JA = '/pickles-02/ja'
PICKLE_FOLDER_LT = '/pickles-02/lt'
PICKLE_FOLDER_NL = '/pickles-02/nl'
PICKLE_FOLDER_PL = '/pickles-02/pl'
PICKLE_FOLDER_PT = '/pickles-02/pt'
PICKLE_FOLDER_TR = '/pickles-02/tr' # Moved from /pickles/tr @ 2026-02-09, T407660

# On pickle_storage03 volume, mounted to /pickles-03
PICKLE_FOLDER_ALS = '/pickles-03/als'
PICKLE_FOLDER_BE = '/pickles-03/be'
PICKLE_FOLDER_BN = '/pickles-03/bn'
PICKLE_FOLDER_CE = '/pickles-03/ce'
PICKLE_FOLDER_CS = '/pickles-03/cs'
PICKLE_FOLDER_DE = '/pickles-03/de' # Moved from /pickles/de @ 2026-02-10, T407660
PICKLE_FOLDER_DSB = '/pickles-03/dsb'
PICKLE_FOLDER_EL = '/pickles-03/el'
PICKLE_FOLDER_EO = '/pickles-03/eo'
PICKLE_FOLDER_ET = '/pickles-03/et'
PICKLE_FOLDER_FA = '/pickles-03/fa'
PICKLE_FOLDER_FI = '/pickles-03/fi'
PICKLE_FOLDER_HI = '/pickles-03/hi'
PICKLE_FOLDER_IA = '/pickles-03/ia'
PICKLE_FOLDER_KA = '/pickles-03/ka'
PICKLE_FOLDER_KK = '/pickles-03/kk'
PICKLE_FOLDER_MS = '/pickles-03/ms'
PICKLE_FOLDER_NO = '/pickles-03/no'
PICKLE_FOLDER_RO = '/pickles-03/ro'
PICKLE_FOLDER_RU = '/pickles-03/ru'
PICKLE_FOLDER_SH = '/pickles-03/sh'
PICKLE_FOLDER_SIMPLE = '/pickles-03/simple'
PICKLE_FOLDER_SK = '/pickles-03/sk'
PICKLE_FOLDER_SQ = '/pickles-03/sq'
PICKLE_FOLDER_SR = '/pickles-03/sr'
PICKLE_FOLDER_SV = '/pickles-03/sv'
PICKLE_FOLDER_UK = '/pickles-03/uk'
PICKLE_FOLDER_UZ = '/pickles-03/uz'
PICKLE_FOLDER_VEC = '/pickles-03/vec'
PICKLE_FOLDER_VI = '/pickles-03/vi'
PICKLE_FOLDER_ZH = '/pickles-03/zh'

REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['anon'] = '100/sec'
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['burst'] = '100/sec'
