from django import template

from tag_parser import template_tag

from fluent_pages.templatetags.fluent_pages_tags import (
    BreadcrumbNode as BaseBreadcrumbNode) 

register = template.Library()


@register.filter
def get_draft_url(url):
    """
    Return the given URL with a draft mode HMAC in its querystring.
    """
    from fluentcms_publishing.utils import get_draft_url

    return get_draft_url(url)


@template_tag(register, 'render_breadcrumb')
class BreadcrumbNode(BaseBreadcrumbNode):
    tag_name = 'render_breadcrumb'
    template_name = 'fluentcms_publishing/parts/breadcrumb.html'
