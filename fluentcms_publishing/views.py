from django.views.generic import ListView
from django.views.generic.detail import DetailView

from .middleware import is_draft_request_context


class PublishingViewMixin(object):

    class Meta:
        abstract = True

    def get_queryset(self):
        return self.model.objects.filter(
            publishing_is_draft=is_draft_request_context).all()


class PublishingDetailView(PublishingViewMixin, DetailView):
    pass


class PublishingListView(PublishingViewMixin, ListView):
    pass
