# -*- coding: utf-8 -*-

from django.db import models
from django.contrib import admin
from django.core.urlresolvers import reverse
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test.utils import override_settings, modify_settings

from django_dynamic_fixture import G

from django_webtest import WebTest

from fluent_pages.models.db import PageLayout

from fluent_contents.models import Placeholder
from fluent_contents.plugins.rawhtml.models import RawHtmlItem

from ..admin import PublishingAdmin
from ..models import PublishingModel
from ..pagetypes.fluentpage.models import FluentPage as Page
from ..utils import create_content_instance, get_draft_hmac#, verify_draft_url, get_draft_url


User = get_user_model()


class ModelM(PublishingModel):
    title = models.CharField(max_length=255)

    class Meta:
        app_label = 'fluentcms_publishing'

admin.site.register(ModelM, PublishingAdmin)
        

class AdminTest(WebTest):
    """ Base utility methods to test interaction with the site admin. """
    csrf_checks = False

    def refresh(self, obj, obj_pk=None):
        """
        Return the same object reloaded from the database, or optinally load
        an arbitrary object by PK if this ID is provided.
        """
        if obj_pk is None:
            obj_pk = obj.pk
        return obj.__class__.objects.get(pk=obj_pk)

    def ct_for_model(self, model_class_or_obj):
        return ContentType.objects.get_for_model(model_class_or_obj)

    def assertNoFormErrorsInResponse(self, response):
        """
        Fail if response content has any lines containing the 'errorlist'
        keyword, which indicates the form submission failed with errors.
        """
        errorlist_messages = [
            l.strip()
            for l in response.text.split('\n')
            if 'errorlist' in l
        ]
        self.assertEqual([], errorlist_messages)

    def admin_publish_item(self, obj, user=None):
        ct = self.ct_for_model(obj)
        admin_app = '_'.join(ct.natural_key())
        response = self.app.get(
            reverse('admin:%s_publish' % admin_app, args=(obj.pk,)),
            user=user,
        )
        self.assertNoFormErrorsInResponse(response)
        self.assertEqual(302, response.status_code)

    def admin_unpublish_item(self, obj, user=None):
        ct = self.ct_for_model(obj)
        admin_app = '_'.join(ct.natural_key())
        response = self.app.get(
            reverse('admin:%s_unpublish' % admin_app, args=(obj.pk,)),
            user=user,
        )
        self.assertNoFormErrorsInResponse(response)
        self.assertEqual(302, response.status_code)


class TestPublishingAdmin(AdminTest):
    """
    Test publishing features via site admin.
    """

    def setUp(self):
        self.staff = G(
            User,
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )

        self.model = ModelM.objects.create(title="O hai, world!")

    def test_publish_model(self):
        # Confirm model is unpublished and versioned as such
        self.assertIsNone(self.model.publishing_linked)

        # Check admin change model includes publish links, not unpublish ones
        response = self.app.get(
            reverse('admin:fluentcms_publishing_modelm_change',
                    args=(self.model.pk, )),
            user=self.staff)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            reverse('admin:fluentcms_publishing_modelm_publish',
                    args=(self.model.pk, )) in response.text)
        self.assertFalse(
            reverse('admin:fluentcms_publishing_modelm_unpublish',
                    args=(self.model.pk, )) in response.text)

        # Publish via admin
        self.admin_publish_item(self.model, user=self.staff)
        self.model = self.refresh(self.model)
        self.assertIsNotNone(self.model.publishing_linked)
        self.assertTrue(self.model.has_been_published)
        self.assertTrue(self.model.get_published().has_been_published)

        # Check admin change model includes unpublish link (published item)
        response = self.app.get(
            reverse('admin:fluentcms_publishing_modelm_change',
                    args=(self.model.pk, )),
            user=self.staff)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            reverse('admin:fluentcms_publishing_modelm_publish',
                    args=(self.model.pk, )) in response.text)
        self.assertTrue(
            reverse('admin:fluentcms_publishing_modelm_unpublish',
                    args=(self.model.pk, )) in response.text)

        # Publish again
        self.model.title += ' - changed'
        self.model.save()
        self.admin_publish_item(self.model, user=self.staff)
        self.model = self.refresh(self.model)

        # Unpublish via admin
        self.admin_unpublish_item(self.model, user=self.staff)

        # New version has unpublished status
        self.model = self.refresh(self.model)
        self.assertIsNone(self.model.publishing_linked)
        self.assertFalse(self.model.has_been_published)

        # Check admin change model includes publish links, not unpublish ones
        response = self.app.get(
            reverse('admin:fluentcms_publishing_modelm_change',
                    args=(self.model.pk, )),
            user=self.staff)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            reverse('admin:fluentcms_publishing_modelm_publish',
                    args=(self.model.pk, )) in response.text)
        self.assertFalse(
            reverse('admin:fluentcms_publishing_modelm_unpublish',
                    args=(self.model.pk, )) in response.text)


@modify_settings(MIDDLEWARE_CLASSES={'append': 'fluentcms_publishing.middleware.PublishingMiddleware'})
class TestPublishingForPageViews(AdminTest):

    def setUp(self):
        self.user = G(User)
        self.admin = G(
            User,
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )
        self.layout = G(
            PageLayout,
            template_path='default.html',
        )
        self.page = Page.objects.create(
            author=self.admin,
            title='Hello, world!',
            slug='hello-world',
            layout=self.layout,
        )
        self.content_instance = create_content_instance(
            RawHtmlItem,
            self.page,
            placeholder_name='content',
            html='<b>lorem ipsum dolor sit amet...</b>'
        )

    def test_url_routing_for_draft_and_published_copies(self):
        # Unpublished page is not visible to anonymous users
        response = self.app.get('/hello-world/', expect_errors=True)
        self.assertEqual(response.status_code, 404)
        # Unpublished page is visible to staff user with '?edit' param redirect
        response = self.app.get(
            '/hello-world/',
            user=self.admin,
        ).follow()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello, world!')

        # Publish page
        self.page.publish()
        self.assertEqual(
            '/hello-world/',
            self.page.get_published().get_absolute_url())

        # Published page is visible to anonymous users
        response = self.app.get('/hello-world/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello, world!')

        # Change Title and slug (URL) of draft page
        self.page.title = 'O hai, world!'
        self.page.slug = 'o-hai-world'
        self.page.save()
        self.page = self.refresh(self.page)
        self.assertEqual(
            '/o-hai-world/', self.page.get_absolute_url())

        # URL of published page remains unchanged
        self.assertEqual(
            '/hello-world/',
            self.page.get_published().get_absolute_url())

        # Published page is at unchanged URL
        response = self.app.get('/hello-world/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello, world!')

        # Draft page is at changed URL
        response = self.app.get(
            '/o-hai-world/',
            user=self.admin,
        ).follow()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'O hai, world!')

        # Draft page is visible at changed URL via ?edit URL
        response = self.app.get(
            '/o-hai-world/?edit',
            user=self.admin,
        ).follow()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'O hai, world!')

        # Draft page is *not* visible at ?edit URL of old (published page) URL
        response = self.app.get(
            '/hello-world/?edit',
            user=self.admin,
        )
        self.assertEqual(response.status_code, 302)
        response = response.follow(expect_errors=True)
        self.assertEqual(response.status_code, 404)

    def test_verified_draft_url_for_publishingmodel(self):
        # Unpublished page is not visible to anonymous users
        response = self.app.get(
            self.page.get_absolute_url(),
            user=self.user,
            expect_errors=True)
        self.assertEqual(response.status_code, 404)
        # Unpublished page is visible to staff user with '?edit' param redirect
        response = self.app.get(
            self.page.get_absolute_url(),
            user=self.admin)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('?edit=' in response['Location'])
        response = response.follow()
        self.assertEqual(response.status_code, 200)
        # Unpublished page is visible to any user with signed '?edit' param
        salt = '123'
        url_hmac = get_draft_hmac(salt, self.page.get_absolute_url())
        response = self.app.get(
            self.page.get_absolute_url() + '?edit=%s:%s' % (
                salt, url_hmac),
            user=self.user)
        self.assertEqual(response.status_code, 200)

        # Publish page
        self.page.publish()

        # Published page is visible to anonymous users
        response = self.app.get(
            self.page.get_absolute_url(),
            user=self.user)
        self.assertEqual(response.status_code, 200)
