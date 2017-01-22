import os

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
    }
]

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

    'publisher',
    'model_settings',
    
    'fluent_pages',

    'fluent_contents',

    'mptt',
    'polymorphic',
    'polymorphic_tree',
    'slug_preview',
    'parler',
] + PROJECT_APPS

ROOT_URLCONF = 'test_urls'

SITE_ID = 1

FLUENT_PAGES_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'test_templates', 'layouts')
