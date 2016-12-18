from django.db import models
from django.utils.translation import ugettext_lazy as _

from parler.models import TranslatedFields

from fluent_pages.models import Page
from fluent_utils.softdeps.any_urlfield import AnyUrlField

from fluentcms_publishing.models import PublishingModel


class RedirectNode(Page, PublishingModel):
    """
    A redirect node
    """
    REDIRECT_TYPE_CHOICES = (
        (302, _("Normal redirect")),
        (301, _("Permanent redirect (for SEO ranking)")),
    )

    # Note that the UrlField can support internal links too when django-any-urlfield is installed.
    redirect_translations = TranslatedFields(
        new_url = AnyUrlField(_("New URL"), max_length=255),
        redirect_type = models.IntegerField(_("Redirect type"), choices=REDIRECT_TYPE_CHOICES, default=302,
            help_text=_("Use 'normal redirect' unless you want to transfer SEO ranking to the new page.")),
    )

    class Meta:
        verbose_name = _("Redirect")
        verbose_name_plural = _("Redirects")

