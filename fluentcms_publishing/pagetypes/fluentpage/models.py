from django.db import models
from django.utils.translation import ugettext_lazy as _

from fluentcms_publishing.models import PublishableFluentContentsPage


class AbstractFluentPage(PublishableFluentContentsPage):
    layout = models.ForeignKey(
        'fluent_pages.PageLayout', verbose_name=_('Layout'), null=True)

    class Meta:
        abstract = True
        verbose_name = _("Page")
        verbose_name_plural = _("Pages")
        permissions = (
            ('change_page_layout', _("Can change Page layout")),
        )


class FluentPage(AbstractFluentPage):
    pass
