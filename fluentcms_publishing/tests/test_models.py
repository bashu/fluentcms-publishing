# -*- coding: utf-8 -*-

from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test.utils import override_settings, modify_settings
from django.test import TestCase, TransactionTestCase

from mock import patch
from django_dynamic_fixture import G

from fluent_pages.models.db import UrlNode

from fluent_contents.models import Placeholder
from fluent_contents.plugins.rawhtml.models import RawHtmlItem

from ..models import PublishingModel, PublishableFluentContents
from ..managers import DraftItemBoobyTrap
from ..pagetypes.fluentpage.models import FluentPage as Page
from ..middleware import (
    override_draft_request_context,
    override_publishing_middleware_active,
)
from ..utils import NotDraftException, PublishingException, create_content_instance

User = get_user_model()


class ModelA(PublishingModel):
    title = models.CharField(max_length=255)

    class Meta:
        app_label = 'fluentcms_publishing'


class ModelB(PublishableFluentContents):
    title = models.CharField(max_length=255)

    class Meta:
        app_label = 'fluentcms_publishing'


class TestPublishingModelAndQueryset(TestCase):

    def setUp(self):
        self.user = G(User)

        self.staff = G(
            User,
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )

        self.model = ModelA.objects.create(title='O hai, world!')

    def test_model_publish_assert_draft_check(self):
        self.model.publish()
        try:
            self.model.get_published().publish()
            self.fail("Expected NotDraftException")
        except NotDraftException:
            pass

    def test_model_publishing_status_attributes(self):
        """
        Test published and draft model status flags, especially the `is_dirty`
        flag and related timestamps that affect the dirty checking logic in
        ``PublishingModelBase.is_dirty``
        """
        draft_instance = self.model
        self.assertIsNone(draft_instance.publishing_linked)
        self.assertIsNone(draft_instance.publishing_published_at)
        self.assertTrue(draft_instance.is_draft)
        self.assertFalse(draft_instance.is_published)
        # An unpublished instance is always considered dirty
        self.assertTrue(draft_instance.is_dirty)

        # Publish instance; check status flags and timestamps are correct
        draft_instance.publish()
        published_instance = draft_instance.publishing_linked
        self.assertIsNotNone(published_instance.publishing_draft)
        self.assertIsNotNone(published_instance.publishing_published_at)
        self.assertFalse(published_instance.is_draft)
        self.assertTrue(published_instance.is_published)
        # A published instance is never dirty
        self.assertFalse(published_instance.is_dirty)

        # Check original draft item has correct status flags after publish
        draft_instance = published_instance.publishing_draft
        self.assertIsNotNone(draft_instance.publishing_linked)
        self.assertIsNotNone(draft_instance.publishing_published_at)
        self.assertTrue(draft_instance.is_draft)
        self.assertFalse(draft_instance.is_published)
        # Publishing timestamps correct?
        self.assertTrue(
            draft_instance.publishing_modified_at <
            draft_instance.publishing_linked.publishing_modified_at)
        # Draft instance is no longer dirty after publishing
        self.assertFalse(draft_instance.is_dirty)

        # Modify the draft item, so published item is no longer up-to-date
        draft_instance.title = draft_instance.title + ' changed'
        draft_instance.save()
        # Draft instance is now dirty after modification
        self.assertTrue(
            draft_instance.publishing_modified_at >
            draft_instance.publishing_linked.publishing_modified_at)
        self.assertTrue(draft_instance.is_dirty)

        # Unpublish instance; check status flags again
        draft_instance.unpublish()
        self.assertIsNone(draft_instance.publishing_linked)
        self.assertIsNone(draft_instance.publishing_published_at)
        self.assertTrue(draft_instance.is_draft)
        self.assertFalse(draft_instance.is_published)
        # Draft instance is dirty after unpublish
        self.assertTrue(draft_instance.is_dirty)

    def test_model_get_visible(self):
        # In non-draft context...
        with patch('fluentcms_publishing.models.is_draft_request_context') as p:
            p.return_value = False
            # Draft-only item returns None for visible
            self.assertIsNone(self.model.get_visible())
            # Published item returns published copy for visible
            self.model.publish()
            self.assertEqual(
                self.model.publishing_linked,
                self.model.get_visible())
            self.assertEqual(
                self.model.publishing_linked,
                self.model.publishing_linked.get_visible())
        # In draft context...
        with patch('fluentcms_publishing.models.is_draft_request_context') as p:
            p.return_value = True
            # Published item returns its draft for visible
            self.assertEqual(
                self.model, self.model.get_visible())
            self.assertEqual(
                self.model,
                self.model.publishing_linked.get_visible())
            # Draft-only item returns itself for visible
            self.model.unpublish()
            self.assertEqual(
                self.model, self.model.get_visible())

    def test_model_is_visible(self):
        with patch('fluentcms_publishing.models.is_draft_request_context') as p:
            # Draft is not visible in non-draft context
            p.return_value = False
            self.assertFalse(self.model.is_visible)
            # Draft is visible in draft context
            p.return_value = True
            self.assertTrue(self.model.is_visible)
        self.model.publish()
        with patch('fluentcms_publishing.models.is_draft_request_context') as p:
            p.return_value = False
            # Draft is not visible in non-draft context
            self.assertFalse(self.model.is_visible)
            # Published copy is visible in non-draft context
            self.assertTrue(self.model.publishing_linked.is_visible)
            p.return_value = True
            # Draft is visible in draft context
            self.assertTrue(self.model.is_visible)
            # Published copy is not visible in draft context (otherwise both
            # draft and published copies of an item could be shown)
            self.assertFalse(self.model.publishing_linked.is_visible)

    def test_model_is_published(self):
        # Only actual published copy returns True for `is_published`
        self.assertFalse(self.model.is_published)
        self.model.publish()
        self.assertFalse(self.model.is_published)
        self.assertTrue(self.model.publishing_linked.is_published)

    def test_queryset_draft_with_publishing_model(self):
        self.assertEqual(
            [self.model], list(ModelA.objects.draft()))
        # Only draft items returned even when published
        self.model.publish()
        self.assertEqual(
            [self.model], list(ModelA.objects.draft()))
        # Confirm we only get draft items regardless of
        # `is_draft_request_context`
        with override_settings(DEBUG=True):
            with patch('fluentcms_publishing.managers.is_draft_request_context') as p:
                p.return_value = False
                self.assertEqual(
                    [self.model], list(ModelA.objects.draft()))

    def test_queryset_published_with_publishing_model(self):
        self.assertEqual(
            [], list(ModelA.objects.published()))
        self.model.publish()
        # Return only published items
        self.assertEqual(
            [self.model.publishing_linked],  # Compare published copy
            list(ModelA.objects.published()))
        # Confirm we only get published items regardless of
        # `is_draft_request_context`
        with patch('fluentcms_publishing.managers.is_draft_request_context') as p:
            p.return_value = True
            self.assertEqual(
                [self.model.publishing_linked],
                list(ModelA.objects.published()))
        # Delegates to `visible` if `for_user` provided
        with patch('fluentcms_publishing.managers.PublishingQuerySet.visible') as p:
            p.return_value = 'success!'
            self.assertEqual(
                'success!',
                ModelA.objects.published(for_user=self.staff))
            self.assertEqual(
                'success!', ModelA.objects.published(for_user=None))
            self.assertEqual(
                'success!', ModelA.objects.published(for_user='whatever'))
        # Confirm draft-for-published exchange is disabled by default...
        self.model.unpublish()
        self.assertEqual(
            set([]), set(ModelA.objects.published()))
        # ... but exchange can be forced
        self.model.publish()
        self.assertEqual(
            set([self.model.publishing_linked]),
            set(ModelA.objects.published(force_exchange=True)))

    def test_queryset_visible(self):
        self.model.publish()
        # In draft mode, `visible` delegates to `draft`
        draft_set = set(ModelA.objects.draft())
        with patch('fluentcms_publishing.managers.is_draft_request_context') as p:
            p.return_value = True
            self.assertEqual(draft_set, set(ModelA.objects.visible()))
        # In non-draft mode, `visible` delegates to `published`
        published_set = set(ModelA.objects.published())
        with patch('fluentcms_publishing.managers.is_draft_request_context') as p:
            p.return_value = False
            self.assertEqual(published_set, set(ModelA.objects.visible()))

    def test_queryset_exchange_for_published(self):
        # Exchanging draft-only items gives no results
        self.assertEqual([self.model], list(ModelA.objects.all()))
        self.assertEqual(
            [], list(ModelA.objects.draft().exchange_for_published()))
        # Exchanging published draft items gives published copies
        self.model.publish()
        self.assertEqual(
            [self.model.publishing_linked],
            list(ModelA.objects.draft().exchange_for_published()))
        # Ordering of items in incoming QS is retained in exchange
        ModelA.objects.create(title='Z')
        ModelA.objects.create(title='Y')
        ModelA.objects.create(title='X')
        ModelA.objects.create(title='W')
        qs = ModelA.objects.order_by('-pk')
        self.assertEqual(
            [p.pk for p in qs.filter(publishing_is_draft=False)],
            [p.pk for p in qs.exchange_for_published()])
        qs = ModelA.objects.order_by('pk')
        self.assertEqual(
            [p.pk for p in qs.filter(publishing_is_draft=False)],
            [p.pk for p in qs.exchange_for_published()])

    def test_draft_item_booby_trap(self):
        # Published item cannot be wrapped by DraftItemBoobyTrap
        self.model.publish()
        try:
            DraftItemBoobyTrap(self.model.get_published())
            self.fail("Expected ValueError wrapping a published item")
        except ValueError, ex:
            self.assertTrue('is not a DRAFT' in ex.message)

        # Wrap draft item
        wrapper = DraftItemBoobyTrap(self.model)

        # Check permitted fields/methods return expected results
        self.assertEqual(self.model, wrapper.get_draft_payload())
        self.assertEqual(
            self.model.get_published(), wrapper.get_published())
        self.assertEqual(
            self.model.get_visible(), wrapper.get_visible())
        self.assertEqual(
            self.model.publishing_linked, wrapper.publishing_linked)
        self.assertEqual(
            self.model.publishing_linked_id,
            wrapper.publishing_linked_id)
        self.assertEqual(
            self.model.publishing_is_draft, wrapper.publishing_is_draft)
        self.assertEqual(
            self.model.is_published, wrapper.is_published)
        self.assertEqual(
            self.model.has_been_published, wrapper.has_been_published)
        self.assertEqual(
            self.model.is_draft, wrapper.is_draft)
        self.assertEqual(
            self.model.is_visible, wrapper.is_visible)
        self.assertEqual(
            self.model.pk, wrapper.pk)

        # Check not-permitted fields/methods raise exception
        try:
            wrapper.title
            self.fail("Expected PublishingException")
        except PublishingException, ex:
            self.assertTrue(
                "Illegal attempt to access 'title' on the DRAFT"
                in ex.message)
        try:
            wrapper.show_title
            self.fail("Expected PublishingException")
        except PublishingException, ex:
            self.assertTrue(
                "Illegal attempt to access 'show_title' on the DRAFT"
                in ex.message)

    def test_queryset_iterator(self):
        self.model.publish()
        # Confirm drafts are wrapped with booby trap on iteration over
        # publishable QS in a public request context.
        with override_publishing_middleware_active(True):
            self.assertTrue(all(
                [i.__class__ == DraftItemBoobyTrap
                    for i in ModelA.objects.all() if i.is_draft]))
            # Published items are never wrapped
            self.assertTrue(all(
                [i.__class__ != DraftItemBoobyTrap
                    for i in ModelA.objects.all() if i.is_published]))
            # Confirm drafts returned as normal when in draft context
            with override_draft_request_context(True):
                self.assertTrue(all(
                    [i.__class__ != DraftItemBoobyTrap
                     for i in ModelA.objects.all() if i.is_draft]))
            # Confirm booby trap works for generic `UrlNode` QS iteration
            self.assertTrue(all(
                [i.__class__ == DraftItemBoobyTrap
                 for i in UrlNode.objects.filter(status=UrlNode.DRAFT)]))
            self.assertTrue(all(
                [i.__class__ != DraftItemBoobyTrap
                 for i in UrlNode.objects.filter(status=UrlNode.PUBLISHED)]))

    def test_queryset_only(self):
        # Check `publishing_is_draft` is always included in `only` filtering
        qs = ModelA.objects.only('pk')
        self.assertEqual(
            set(['id', 'publishing_is_draft']),
            qs.query.get_loaded_field_names()[ModelA])
        qs = ModelA.objects.only('id', 'publishing_is_draft')
        self.assertEqual(
            set(['id', 'publishing_is_draft']),
            qs.query.get_loaded_field_names()[ModelA])

    def test_model_get_draft(self):
        self.model.publish()
        self.assertEqual(
            self.model, self.model.get_draft())
        self.assertEqual(
            self.model, self.model.publishing_linked.get_draft())
        self.assertEqual(
            self.model,
            self.model.publishing_linked.publishing_draft.get_draft())
        # Ensure raw `publishing_draft` relationship also returns plain draft
        self.assertEqual(
            self.model,
            self.model.publishing_linked.publishing_draft)

        # get_draft always returns the unwrapped draft
        # TODO Beware, these tests never triggered actual failure case, and
        # should be unnecessary given the model equality tests above
        self.assertFalse(isinstance(self.model.get_draft(), DraftItemBoobyTrap))
        self.assertFalse(isinstance(self.model.publishing_linked.get_draft(), DraftItemBoobyTrap))
        self.assertFalse(isinstance(self.model.publishing_linked.publishing_draft.get_draft(), DraftItemBoobyTrap))

    def test_model_get_published(self):
        self.assertIsNone(self.model.get_published())
        self.model.publish()
        self.assertEqual(
            self.model.publishing_linked,
            self.model.get_published())
        self.assertEqual(
            self.model.publishing_linked,
            self.model.publishing_linked.get_published())


class TestPublishableFluentContentsPage(TestCase):
    """ Test publishing features with a Fluent Contents Page """

    def setUp(self):
        self.user = G(User)

        self.staff = G(
            User,
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )

        self.page = Page.objects.create(
            author=self.user,
            title='O hai, world!',
        )
        self.placeholder = Placeholder.objects.create_for_object(
            self.page,
            slot='lorem-ipsum',
            role='l',
            title='Lorem ipsum dolor sit amet...',
        )

    def test_contentitems_and_placeholders_cloned_on_publish(self):
        # Associate content items with page
        ping = create_content_instance(
            RawHtmlItem,
            self.page,
            placeholder_name='lorem-ipsum',
            html='<b>ping</b>'
        )
        pong = create_content_instance(
            RawHtmlItem,
            self.page,
            placeholder_name='lorem-ipsum',
            html='<b>pong</b>'
        )
        self.assertEqual(
            2, self.page.contentitem_set.count())
        self.assertEqual(
            list(self.page.contentitem_set.all()),
            [ping, pong])
        self.assertEqual(
            [i.html for i in self.page.contentitem_set.all()],
            ['<b>ping</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder for i in self.page.contentitem_set.all()],
            [self.placeholder, self.placeholder])
        self.assertEqual(
            [i.placeholder.slot
             for i in self.page.contentitem_set.all()],
            ['lorem-ipsum', 'lorem-ipsum'])
        # Publish page
        self.page.publish()
        published_page = self.page.publishing_linked
        self.assertNotEqual(
            self.page.pk, published_page.pk)
        # Confirm published page has cloned content items and placeholders
        # (with different model instances (PKs) but same content)
        self.assertEqual(
            2, published_page.contentitem_set.count())
        self.assertNotEqual(
            list(published_page.contentitem_set.all()),
            [ping, pong])
        self.assertEqual(
            [i.html for i in published_page.contentitem_set.all()],
            ['<b>ping</b>', '<b>pong</b>'])
        self.assertNotEqual(
            [i.placeholder for i in published_page.contentitem_set.all()],
            [self.placeholder, self.placeholder])
        self.assertEqual(
            [i.placeholder.slot
             for i in published_page.contentitem_set.all()],
            ['lorem-ipsum', 'lorem-ipsum'])
        # Modify content items and placeholders for draft page
        ping.html = '<b>ping - updated</b>'
        ping.save()
        self.placeholder.slot = 'lorem-ipsum-updated'
        self.placeholder.save()
        self.page.save()  # Trigger timestamp change in draft page
        self.assertEqual(
            [i.html for i in self.page.contentitem_set.all()],
            ['<b>ping - updated</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder.slot
             for i in self.page.contentitem_set.all()],
            ['lorem-ipsum-updated', 'lorem-ipsum-updated'])
        # Confirm content items for published copy remain unchanged
        published_page = self.page.publishing_linked
        self.assertEqual(
            [i.html for i in published_page.contentitem_set.all()],
            ['<b>ping</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder.slot
             for i in published_page.contentitem_set.all()],
            ['lorem-ipsum', 'lorem-ipsum'])
        # Re-publish page
        self.page.publish()
        published_page = self.page.publishing_linked
        # Confirm published page has updated content items
        self.assertEqual(
            [i.html for i in published_page.contentitem_set.all()],
            ['<b>ping - updated</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder.slot
             for i in published_page.contentitem_set.all()],
            ['lorem-ipsum-updated', 'lorem-ipsum-updated'])

    def test_model_is_within_publication_dates(self):
        # Empty publication start/end dates
        self.assertTrue(self.page.is_within_publication_dates())
        # Test publication start date
        self.page.publication_date = timezone.now() - timedelta(seconds=1)
        self.page.save()
        self.assertTrue(self.page.is_within_publication_dates())
        self.page.publication_date = timezone.now() + timedelta(seconds=1)
        self.page.save()
        self.assertFalse(self.page.is_within_publication_dates())
        # Reset
        self.page.publication_date = None
        self.page.save()
        self.assertTrue(self.page.is_within_publication_dates())
        # Test publication end date
        self.page.publication_end_date = \
            timezone.now() + timedelta(seconds=1)
        self.page.save()
        self.assertTrue(self.page.is_within_publication_dates())
        self.page.publication_end_date = \
            timezone.now() - timedelta(seconds=1)
        self.page.save()
        self.assertFalse(self.page.is_within_publication_dates())
        # Reset
        self.page.publication_end_date = None
        self.page.save()
        self.assertTrue(self.page.is_within_publication_dates())
        # Test both publication start and end dates against arbitrary timestamp
        self.page.publication_date = timezone.now() - timedelta(seconds=1)
        self.page.publication_end_date = \
            timezone.now() + timedelta(seconds=1)
        self.assertTrue(self.page.is_within_publication_dates())
        self.assertTrue(
            self.page.is_within_publication_dates(timezone.now()))
        # Timestamp exactly at publication start date is acceptable
        self.assertTrue(
            self.page.is_within_publication_dates(
                self.page.publication_date))
        # Timestamp exactly at publication end date is not acceptable
        self.assertFalse(
            self.page.is_within_publication_dates(
                self.page.publication_end_date))

    def test_queryset_published_with_urlnode_based_publishing_model(self):
        self.assertEqual(
            [], list(Page.objects.published()))
        self.page.publish()
        # Return only published items
        self.assertEqual(
            [self.page.publishing_linked],  # Compare published copy
            list(Page.objects.published()))
        # Confirm we only get published items regardless of
        # `is_draft_request_context`
        with patch('fluentcms_publishing.apps.is_draft_request_context') as p:
            p.return_value = True
            self.assertEqual(
                [self.page.publishing_linked],
                list(Page.objects.published()))
        # Delegates to `visible` if `for_user` provided
        with patch('fluentcms_publishing.managers.PublishingQuerySet.visible') as p:
            p.return_value = 'success!'
            self.assertEqual(
                'success!',
                Page.objects.published(for_user=self.staff))
            self.assertEqual(
                'success!', Page.objects.published(for_user=None))
            self.assertEqual(
                'success!', Page.objects.published(for_user='whatever'))
        # Confirm draft-for-published exchange is disabled by default...
        self.page.unpublish()
        self.assertEqual(
            set([]), set(Page.objects.published()))
        # ... but exchange can be forced
        self.page.publish()
        self.assertEqual(
            set([self.page.publishing_linked]),
            set(Page.objects.published(force_exchange=True)))

    def test_fluent_page_model_get_draft(self):
        self.page.publish()
        self.assertEqual(
            self.page, self.page.get_draft())
        self.assertEqual(
            self.page, self.page.publishing_linked.get_draft())
        self.assertEqual(
            self.page,
            self.page.publishing_linked.publishing_draft.get_draft())
        # Ensure raw `publishing_draft` relationship also returns plain draft
        self.assertEqual(
            self.page,
            self.page.publishing_linked.publishing_draft)


class TestPublishableFluentContents(TestCase):
    """ Test publishing features with a Fluent Contents item (not a page) """

    def setUp(self):
        self.user = G(User)
        self.staff = G(
            User,
            is_staff=True,
            is_active=True,
            is_superuser=True,
        )

        self.fluent_contents = ModelB.objects.create(
            title='Lorem ipsum dolor sit amet..',
        )
        self.placeholder = Placeholder.objects.create_for_object(
            self.fluent_contents,
            slot='lorem-ipsum',
            role='l',
            title='Lorem ipsum dolor sit amet...',
        )

    def test_contentitems_and_placeholders_cloned_on_publish(self):
        # Associate content items with page
        ctype = ContentType.objects.get_for_model(ModelB)
        ping = RawHtmlItem.objects.create(
            parent_type=ctype,
            parent_id=self.fluent_contents.id,
            placeholder=self.placeholder,
            html='<b>ping</b>'
        )
        pong = RawHtmlItem.objects.create(
            parent_type=ctype,
            parent_id=self.fluent_contents.id,
            placeholder=self.placeholder,
            html='<b>pong</b>'
        )
        self.assertEqual(
            2, self.fluent_contents.contentitem_set.count())
        self.assertEqual(
            list(self.fluent_contents.contentitem_set.all()),
            [ping, pong])
        self.assertEqual(
            [i.html for i in self.fluent_contents.contentitem_set.all()],
            ['<b>ping</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder for i in self.fluent_contents.contentitem_set.all()],
            [self.placeholder, self.placeholder])
        self.assertEqual(
            [i.placeholder.slot
             for i in self.fluent_contents.contentitem_set.all()],
            ['lorem-ipsum', 'lorem-ipsum'])
        # Publish page
        self.fluent_contents.publish()
        published_page = self.fluent_contents.publishing_linked
        self.assertNotEqual(
            self.fluent_contents.pk, published_page.pk)
        # Confirm published page has cloned content items and placeholders
        # (with different model instances (PKs) but same content)
        self.assertEqual(
            2, published_page.contentitem_set.count())
        self.assertNotEqual(
            list(published_page.contentitem_set.all()),
            [ping, pong])
        self.assertEqual(
            [i.html for i in published_page.contentitem_set.all()],
            ['<b>ping</b>', '<b>pong</b>'])
        self.assertNotEqual(
            [i.placeholder for i in published_page.contentitem_set.all()],
            [self.placeholder, self.placeholder])
        self.assertEqual(
            [i.placeholder.slot
             for i in published_page.contentitem_set.all()],
            ['lorem-ipsum', 'lorem-ipsum'])
        # modify content items and placeholders for draft page
        ping.html = '<b>ping - updated</b>'
        ping.save()
        self.placeholder.slot = 'lorem-ipsum-updated'
        self.placeholder.save()
        self.fluent_contents.save()  # Trigger timestamp change in draft page
        self.assertEqual(
            [i.html for i in self.fluent_contents.contentitem_set.all()],
            ['<b>ping - updated</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder.slot
             for i in self.fluent_contents.contentitem_set.all()],
            ['lorem-ipsum-updated', 'lorem-ipsum-updated'])
        # Confirm content items for published copy remain unchanged
        published_page = self.fluent_contents.publishing_linked
        self.assertEqual(
            [i.html for i in published_page.contentitem_set.all()],
            ['<b>ping</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder.slot
             for i in published_page.contentitem_set.all()],
            ['lorem-ipsum', 'lorem-ipsum'])
        # Re-publish page
        self.fluent_contents.publish()
        published_page = self.fluent_contents.publishing_linked
        # Confirm published page has updated content items
        self.assertEqual(
            [i.html for i in published_page.contentitem_set.all()],
            ['<b>ping - updated</b>', '<b>pong</b>'])
        self.assertEqual(
            [i.placeholder.slot
             for i in published_page.contentitem_set.all()],
            ['lorem-ipsum-updated', 'lorem-ipsum-updated'])


class TestDjangoDeleteCollectorPatchForProxyModels(TransactionTestCase):
    """
    Make sure we can delete the whole object tree for Fluent pages, or other
    similar models, that have non-abstract Proxy model instance ancestors
    and where a relationship exists to the proxy ancestor.  Django does not
    otherwise properly collect and delete the proxy model's DB record in this
    case, at least prior to 1.10.
    These tests will fail if the monkey-patches like
    `APPLY_patch_django_18_get_candidate_relations_to_delete` are not applied
    with error like:
        IntegrityError: update or delete on table "fluent_pages_urlnode"
        violates foreign key constraint
        "fluent_pa_master_id_5300b55ee85000a1_fk_fluent_pages_urlnode_id" on
        table "fluent_pages_htmlpage_translation" DETAIL:  Key (id)=(2) is
        still referenced from table "fluent_pages_htmlpage_translation".
    """
    # Set `available_apps` here merely to trigger special behaviour in
    # `TransactionTestCase._fixture_teardown` to avoid emitting the
    # `post_migrate` signal when flushing the DB during teardown, since doing
    # so can cause integrity errors related to publishing-related permissions
    # created by icekit.publishing.models.create_can_publish_permission
    available_apps = settings.INSTALLED_APPS

    def setUp(self):
        self.user = G(User)

        self.page = Page.objects.create(
            title='O hai, world!', author=self.user,
        )

    def tearDown(self):
        Page.objects.all().delete()

    # Test to trigger DB integrity errors if Fluent Page deletion is not
    # properly handled/patched
    def test_republish_page(self):
        # Publish first version
        self.page.publish()
        self.assertEqual(
            'O hai, world!', self.page.get_published().title)
        # Re-publish page, to trigger deletion and recreation of published
        # copy
        self.page.title += ' - Updated'
        self.page.save()
        self.page.publish()
        self.assertEqual(
            'O hai, world! - Updated',
            self.page.get_published().title)
