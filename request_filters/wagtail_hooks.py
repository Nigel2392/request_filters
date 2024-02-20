from django.utils.translation import gettext_lazy as _
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import FilteredRequest

class FilteredRequestViewSet(SnippetViewSet):
    model = FilteredRequest
    copy_view_enabled = False

    icon = 'clipboard-list'
    menu_order = 1500
    menu_name = "request_filters_log"
    menu_label = _("Request Filters Log")
    add_to_settings_menu = True

    list_display = (
        'get_list_title',
        'get_list_description',
        'get_match_performed',
        'created_at',
    )
    

register_snippet(FilteredRequest, FilteredRequestViewSet)



