import os

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

PROJECT_APPS = [
    'fluentcms_publishing',
    'fluentcms_publishing.pagetypes.fluentpage',
    'fluentcms_publishing.pagetypes.redirectnode',
]

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.sites',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.contenttypes',
    'django.contrib.admin',

    'publisher',
    'model_settings',
    
    'fluent_pages',

    'fluent_contents',
    'fluent_contents.plugins.rawhtml',

    'mptt',
    'polymorphic',
    'polymorphic_tree',
    'slug_preview',
    'parler',
] + PROJECT_APPS

MIDDLEWARE_CLASSES = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

TEMPLATE_DIRS = [
    os.path.join(os.path.dirname(__file__), 'test_templates', 'layouts'),
]

TEMPLATE_CONTEXT_PROCESSORS = [
    'django.contrib.auth.context_processors.auth',
    'django.template.context_processors.debug',
    'django.template.context_processors.i18n',
    'django.template.context_processors.media',
    'django.template.context_processors.static',
    'django.template.context_processors.tz',
    'django.template.context_processors.request',
    'django.contrib.messages.context_processors.messages',
]

ROOT_URLCONF = 'test_urls'

SITE_ID = 1

STATIC_URL = '/static/'

FLUENT_PAGES_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'test_templates', 'layouts')
