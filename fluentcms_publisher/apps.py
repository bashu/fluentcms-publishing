# -*- coding: utf-8 -*-

from django.conf import settings
from django.apps import AppConfig


class DefaultConfig(AppConfig):
    label = name = 'fluentcms_publisher'

    def ready(self):
        if 'fluent_pages' in settings.INSTALLED_APPS:
            pass
