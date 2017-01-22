# -*- coding: utf-8 -*-

from django.test import TestCase
from django.contrib.sites.models import Site
from django.contrib.auth import get_user_model

from django_dynamic_fixture import G

from fluentcms_publishing.pagetypes.fluentpage.models import FluentPage as Page

from ..utils import NotDraftException

User = get_user_model()


class TestPublishingModelAndQueryset(TestCase):

    def setUp(self):
        self.site, __ = Site.objects.get_or_create(
            pk=1, defaults={'name': 'example.com', 'domain': 'example.com'})

        self.user = G(User)

        self.staff = G(
            User,
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )

        self.page = Page.objects.create(
            title='O hai, world!', author=self.staff,
        )

    def test_model_publish_assert_draft_check(self):
        self.page.publish()
        try:
            self.page.get_published().publish()
            self.fail("Expected NotDraftException")
        except NotDraftException:
            pass
