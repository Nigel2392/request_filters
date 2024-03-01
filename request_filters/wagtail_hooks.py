import json
from typing import Any
from django.db import models
from django.utils import timezone
from django.urls import path, reverse
from django.views.generic import TemplateView
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest, HttpResponse

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail.admin.views.generic import WagtailAdminTemplateMixin
from wagtail.admin.widgets.button import HeaderButton
from wagtail import hooks

from .models import FilteredRequest, FilterSettings, FilterActionChoices
from .options import RequestFilters

class FilteredRequestViewSet(SnippetViewSet):
    model = FilteredRequest
    copy_view_enabled = False

    icon = 'clipboard-list'
    menu_order = 1500
    menu_name = "request_filters_log"
    menu_label = _("Request Filters Log")
    add_to_admin_menu = False
    add_to_settings_menu = False
    url_prefix = 'request_filters/log'
    admin_url_namespace = 'request_filters_log'

    list_display = (
        'get_list_title',
        'get_list_description',
        'get_match_performed',
        'created_at',
    )
    
register_snippet(FilteredRequest, FilteredRequestViewSet)


class URL(object):
    def __init__(self, url: str, label: str, reverse_kwargs: dict = None):
        if (reverse_kwargs is not None) and (reverse_kwargs is not True):
            url = reverse(url, kwargs=reverse_kwargs)
        elif reverse_kwargs is True:
            url = reverse(url)

        self.url = url
        self.label = label

    def keys(self):
        return ['url', 'label']

    def __getitem__(self, key):
        return getattr(self, key)

class FilteredRequestChartView(WagtailAdminTemplateMixin, TemplateView):
    template_name = 'request_filters/chart_view.html'
    page_title = _('Filters Chart')
    page_subtitle = _('Analyse your filters')
    header_icon = 'clipboard-list'
    _show_breadcrumbs = True
    days = 7

    def get_breadcrumbs_items(self):

        if self.request.user.has_perms([
                    f"{FilterSettings._meta.app_label}.change_{FilterSettings._meta.model_name}",
                ]):

            return [
                URL("wagtailsettings:edit", _("Settings"), {"app_name": FilterSettings._meta.app_label, "model_name": FilterSettings._meta.model_name}),
                URL("filter_chart_view", _("Analyse your Filters"), True),
            ]
        
        return [
            URL("filter_chart_view", _("Analyse your Filters"), True),
        ]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:

        annotations = {}
        for action, _ in FilterActionChoices.choices:
            annotations[f'count_{action.lower()}'] = models.Count(
                '_filter',
                filter=models.Q(
                    _filter__action=action
                ),
            )


        requests = FilteredRequest.objects.all()\
            .filter(created_at__gte=timezone.now() - timezone.timedelta(days=self.days))\
            .values(date=models.functions.TruncDate('created_at'))\
            .annotate(**annotations)\
            .values_list('date', *annotations.keys())\
            .order_by('date')
        
        end_date = timezone.now().date()
        start_date = end_date - timezone.timedelta(days=self.days)
        date_range = [start_date + timezone.timedelta(days=x) for x in range((end_date - start_date).days + 1)]

        labels = [date for date in date_range]
        datasets = []
        for i, (action, _) in enumerate(FilterActionChoices.choices):
            dataset = {'label': action, 'data': []}
            data_points = {request[0]: request[i + 1] for request in requests}

            for date in date_range:
                dataset['data'].append({
                    'x': date,
                    'y': data_points.get(date, 0),
                })

            datasets.append(dataset)

        chart = {
            "datasets": datasets,
            "labels": labels,
        }
        return self.render_to_response(
            context=self.get_context_data(
                chart = json.dumps(chart, cls=DjangoJSONEncoder),
            ),
        )


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [
        path('filter-chart/', FilteredRequestChartView.as_view(), name='filter_chart_view'),
    ]


from wagtail.contrib.settings.registry import SettingMenuItem
from wagtail.admin.menu import (
    Menu, SubmenuMenuItem, MenuItem,
)


filters_menu = Menu(
    register_hook_name='register_filters_menu_item',
    construct_hook_name='construct_filters_menu',
)


@hooks.register('register_filters_menu_item')
def register_filters_menu_item():
    return MenuItem(
        _('Analyse'),
        url=reverse('filter_chart_view'),
        icon_name="filters-chart",
        order=1,
    )

@hooks.register('register_filters_menu_item')
def register_settings_menu_item():
    return SettingMenuItem(
        model=FilterSettings,
        icon="sliders",
        name="request_filters_settings",
        order=2,
    )

@hooks.register('register_filters_menu_item')
def register_settings_menu_item():
    return FilteredRequestViewSet().get_menu_item(
        order=3,
    )

@hooks.register(RequestFilters.REGISTER_TO_MENU)
def register_admin_menu_item():
    return SubmenuMenuItem(
        _('Request Filters'),
        icon_name='filters-firewall',
        name='request_filters',
        menu=filters_menu,
        order=100,
    )

@hooks.register("register_icons")
def register_icons(icons):
    return icons + [
        'request_filters/filters-chart.svg',
        'request_filters/filters-firewall.svg',
    ]

@hooks.register("construct_settings_menu")
def construct_settings_menu(request, items):
    items[:] = [item for item in items if item.name != "request_filters_settings_disabled"]
    return items
