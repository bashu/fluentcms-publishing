from django import template

register = template.Library()


@register.filter
def get_draft_url(url):
    """
    Return the given URL with a draft mode HMAC in its querystring.
    """
    from fluentcms_publishing.utils import get_draft_url

    return get_draft_url(url)
