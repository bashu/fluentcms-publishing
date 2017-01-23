# -*- coding: utf-8 -*-

import urlparse

from django.core.urlresolvers import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.http import HttpResponseNotFound, QueryDict
from django.test import TestCase, RequestFactory

from mock import Mock
from django_dynamic_fixture import G

from ..managers import DraftItemBoobyTrap
from ..middleware import (
    PublishingMiddleware,
    is_publishing_middleware_active,
    get_current_user,
    is_draft_request_context,
    override_current_user,
)
from ..utils import get_draft_hmac, verify_draft_url, get_draft_url

User = get_user_model()


class TestPublishingMiddleware(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

        self.response = Mock()

        self.staff = G(
            User,
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )

        self.user = G(
            User,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )

        self.reviewer = G(
            User,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        group, __ = Group.objects.get_or_create(name='Content Reviewers')
        self.reviewer.groups.add(group)

    def _request(self, path='/wherever/', data=None, user=None):
        request = self.factory.get(path, data)
        request.user = user or AnonymousUser()
        return request

    def test_middleware_method_is_admin_request(self):
        # Admin.
        request = self._request(reverse('admin:index'), user=self.staff)
        self.assertTrue(PublishingMiddleware.is_admin_request(request))
        # Not admin.
        request = self._request('/not-admin/', user=self.staff)
        self.assertFalse(PublishingMiddleware.is_admin_request(request))

    def test_middleware_method_is_staff_user(self):
        # Staff.
        request = self._request(user=self.staff)
        self.assertTrue(PublishingMiddleware.is_staff_user(request))
        # Reviewer.
        request = self._request(user=self.reviewer)
        self.assertFalse(PublishingMiddleware.is_staff_user(request))
        # Anonymous.
        self.assertFalse(
            PublishingMiddleware.is_staff_user(self._request()))

    def test_middleware_method_is_draft_request(self):
        # The `is_draft_request(request)` middleware method only checks if the
        # 'edit' flag is present in the querystring. So for content reviewers,
        # who *always* see draft content, their requests don't have the 'edit'
        # flag and so they will never be "draft requests". Confusingly, the
        # `is_draft(request)` is the one that determines the actual draft
        # status of a request!

        # Staff, with 'edit' flag.
        request = self._request(data={'edit': ''}, user=self.staff)
        self.assertTrue(PublishingMiddleware.is_draft_request(request))
        # Reviewer, with 'edit' flag.
        request = self._request(data={'edit': ''}, user=self.reviewer)
        self.assertTrue(PublishingMiddleware.is_draft_request(request))
        # Anonymous, with 'edit' flag.
        request = self._request(data={'edit': ''})
        self.assertTrue(PublishingMiddleware.is_draft_request(request))

        # Staff, without 'edit' flag.
        request = self._request(user=self.staff)
        self.assertFalse(PublishingMiddleware.is_draft_request(request))
        # Reviewer, without 'edit' flag.
        request = self._request(user=self.reviewer)
        self.assertFalse(PublishingMiddleware.is_draft_request(request))
        # Anonymous, without 'edit' flag.
        request = self._request()
        self.assertFalse(PublishingMiddleware.is_draft_request(request))

    def test_middleware_method_is_draft(self):
        # Admin requests are always draft.
        request = self._request(reverse('admin:index'), user=self.staff)
        self.assertTrue(PublishingMiddleware.is_draft(request))

        # Requests from content reviewers are draft, with the 'edit' flag...
        request = self._request(data={'edit': ''}, user=self.reviewer)
        self.assertTrue(PublishingMiddleware.is_draft(request))
        # ...and without.
        request = self._request(user=self.reviewer)
        self.assertTrue(PublishingMiddleware.is_draft(request))

        # Staff can request draft...
        request = self._request(data={'edit': ''}, user=self.staff)
        self.assertTrue(PublishingMiddleware.is_draft(request))
        # ...or published.
        request = self._request(user=self.staff)
        self.assertFalse(PublishingMiddleware.is_draft(request))

        # Draft flag is ignored for unprivileged users.
        request = self._request(data={'edit': ''}, user=self.user)
        self.assertFalse(PublishingMiddleware.is_draft(request))

        # Draft flag is honored for anonymous users if it has a valid draft
        # mode HMAC...
        request = self._request(
            '/', data={'edit': '%s:%s' % (1, get_draft_hmac(1, '/'))})
        self.assertTrue(PublishingMiddleware.is_draft(request))
        # ...and ignored if it is invalid.
        request = self._request('/', data={'edit': '1:abc'})
        self.assertFalse(PublishingMiddleware.is_draft(request))

    def test_middleware_active_status(self):
        mw = PublishingMiddleware()

        # Request processing sets middleware active flag
        mw.process_request(self._request())
        self.assertTrue(mw.is_publishing_middleware_active())
        self.assertTrue(is_publishing_middleware_active())

        # Response processing clears middleware active flag
        mw.process_response(self._request(), self.response)
        self.assertFalse(mw.is_publishing_middleware_active())
        self.assertFalse(is_publishing_middleware_active())

    def test_middleware_current_user(self):
        mw = PublishingMiddleware()

        # Request processing sets current user, AnonymousUser by default
        mw.process_request(self._request())
        self.assertTrue(mw.get_current_user().is_anonymous())
        self.assertTrue(get_current_user().is_anonymous())

        # Request processing sets current user when provided
        mw.process_request(self._request(user=self.reviewer))
        self.assertEqual(mw.get_current_user(), self.reviewer)
        self.assertEqual(get_current_user(), self.reviewer)

        # Test context manager override
        mw.process_request(self._request(user=self.reviewer))
        with override_current_user(AnonymousUser()):
            self.assertTrue(mw.get_current_user().is_anonymous())
            self.assertTrue(get_current_user().is_anonymous())

        # Response processing clears current user
        mw.process_response(self._request(), self.response)
        self.assertIsNone(mw.get_current_user())
        self.assertIsNone(get_current_user())

    def test_middleware_edit_param_triggers_draft_request_context(self):
        mw = PublishingMiddleware()

        # Request processing normal URL does not trigger draft status
        mw.process_request(self._request())
        self.assertFalse(mw.is_draft_request_context())
        self.assertFalse(is_draft_request_context())

        # Request URL from Content Reviewers is always draft, no 'edit' req'd
        request = self._request(user=self.reviewer)
        mw.process_request(request)
        self.assertTrue(mw.is_draft_request_context())
        self.assertTrue(is_draft_request_context())

        # Request URL with 'edit' param triggers draft for staff
        request = self._request(data={'edit': ''}, user=self.staff)
        mw.process_request(request)
        self.assertTrue(mw.is_draft_request_context())
        self.assertTrue(is_draft_request_context())

        # Non-privileged users cannot trigger draft mode with 'edit' param
        request = self._request(data={'edit': ''}, user=self.user)
        mw.process_request(self._request())
        self.assertFalse(mw.is_draft_request_context())
        self.assertFalse(is_draft_request_context())

        # Response processing clears draft status
        mw.process_response(self._request(), self.response)
        self.assertFalse(mw.is_draft_request_context())
        self.assertFalse(is_draft_request_context())

    def test_middleware_draft_view_sets_request_flag(self):
        mw = PublishingMiddleware()

        # Request normal URL sets IS_DRAFT to False
        request = self._request()
        mw.process_request(request)
        self.assertFalse(request.IS_DRAFT)

        # Request URL from Content Reviewer sets IS_DRAFT to True
        request = self._request(user=self.reviewer)
        mw.process_request(request)
        self.assertTrue(request.IS_DRAFT)

        # Request URL without param from staff sets IS_DRAFT to False
        request = self._request(user=self.staff)
        mw.process_request(request)
        self.assertFalse(request.IS_DRAFT)

        # Request URL with 'edit' param from staff sets IS_DRAFT to True
        request = self._request(
            '/',
            data={'edit': '%s:%s' % (1, get_draft_hmac(1, '/'))},
            user=self.staff,
        )
        mw.process_request(request)
        self.assertTrue(request.IS_DRAFT)

    def test_middleware_redirect_staff_to_draft_mode(self):
        # If staff use the 'edit' flag, it is automatically populated with a
        # valid draft mode HMAC, making the URL shareable.
        mw = PublishingMiddleware()

        # Empty 'edit' flag are populated.
        request = self._request(data={'edit': ''}, user=self.staff)
        response = mw.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(verify_draft_url(response['Location']))

        # Invalid 'edit' flags are corrected.
        request = self._request(data={'edit': '1:abc'}, user=self.staff)
        response = mw.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(verify_draft_url(response['Location']))

        # Non-ASCII query string values are supported by draft context URL
        # processing methods, so they don't raise "UnicodeEncodeError: 'ascii'
        # codec can't encode character..." exceptions when a unicode location
        # value is provided
        try:
            verify_draft_url(u"/search/?q=Eugène O'keeffe")
        except UnicodeEncodeError:
            self.fail("verify_draft_url mishandles non-ASCII unicode text")
        try:
            get_draft_url(u"/search/?q=Eugène O'keeffe")
        except UnicodeEncodeError:
            self.fail("get_draft_url mishandles non-ASCII unicode text")

    def test_middleware_redirect_staff_to_draft_view_on_404(self):
        mw = PublishingMiddleware()

        # 404 response for staff redirects to draft and retains GET params.
        request = self._request(data={'x': 'y', 'a': '432'}, user=self.staff)
        response = mw.process_response(request, HttpResponseNotFound())
        self.assertEqual(302, response.status_code)
        query = QueryDict(urlparse.urlparse(response['Location']).query)
        self.assertIn('edit', query)
        self.assertEqual(query['x'], 'y')
        self.assertEqual(query['a'], '432')

        # 404 response for draft view does not redirect
        request = self._request(data={'edit': ''}, user=self.staff)
        response = mw.process_response(request, HttpResponseNotFound())
        self.assertEqual(404, response.status_code)

        # 404 response for admin view does not redirect
        request = self._request(reverse('admin:index'), user=self.staff)
        response = mw.process_response(request, HttpResponseNotFound())
        self.assertEqual(404, response.status_code)

        # 404 response for content reviewer does not redirect, no point
        request = self._request(user=self.reviewer)
        response = mw.process_response(request, HttpResponseNotFound())
        self.assertEqual(404, response.status_code)

        # 404 response for general public does not redirect to draft view
        request = self._request(user=self.user)
        response = mw.process_response(request, HttpResponseNotFound())
        self.assertEqual(404, response.status_code)
 
