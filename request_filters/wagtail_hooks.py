import datetime
from typing import Any
from django import forms
from django.db import models
from django.utils import timezone
from django.urls import path, reverse
from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _, gettext_lazy
from django.http import HttpRequest, HttpResponse

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail.admin.views.generic import WagtailAdminTemplateMixin
from wagtail.admin.widgets.button import Button, ButtonWithDropdown, HeaderButton
from wagtail import hooks

from django_filters.filterset import FilterSet
from django_filters import filters

from .checks import FilterChoices, FilterMethodChoices
from .models import FilteredRequest, FilterSettings, Filter, FilterActionChoices
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

def _positive(number: int, add: int = 24, zero: int = 0) -> int:
    return number if number >= zero else add + number

weekdays = {
    1: gettext_lazy("Monday"),
    2: gettext_lazy("Tuesday"),
    3: gettext_lazy("Wednesday"),
    4: gettext_lazy("Thursday"),
    5: gettext_lazy("Friday"),
    6: gettext_lazy("Saturday"),
    7: gettext_lazy("Sunday"),
}

months = {
    1: gettext_lazy("January"),
    2: gettext_lazy("February"),
    3: gettext_lazy("March"),
    4: gettext_lazy("April"),
    5: gettext_lazy("May"),
    6: gettext_lazy("June"),
    7: gettext_lazy("July"),
    8: gettext_lazy("August"),
    9: gettext_lazy("September"),
    10: gettext_lazy("October"),
    11: gettext_lazy("November"),
    12: gettext_lazy("December"),
}

def day_to_weekday(request, point):
    return weekdays[point]

def integer_to_month(request, point):
    return months[point]

def _hour_data(self_day, annotations, requests):
    requests = requests.values(date=models.functions.ExtractHour('created_at'))\
        .annotate(**annotations)\
        .values_list('date', *annotations.keys())\
        .order_by('date')

    hour_end = timezone.now().hour
    hour_start = hour_end - 24
    # Needs to be hour + 1 to avoid inaccurate data
    labels = [_positive(hour + 1, 24) for hour in range(hour_start + 1, hour_end + 1)]
    return labels, requests, lambda request, point: f"{point}:00"

def _week_data(self_day, annotations, requests):
    requests = requests.values(date=models.functions.ExtractIsoWeekDay('created_at'))\
        .annotate(**annotations)\
        .values_list('date', *annotations.keys())\
        .order_by('date')

    end_date = timezone.now().date().isoweekday()
    start_date = end_date - 7
    labels = [_positive(start_date + x, 7, zero=1) for x in range(1, 8)]
    
    return labels, requests, day_to_weekday,

def _date_data(self_day, annotations, requests):
    requests = requests.values(date=models.functions.TruncDate('created_at'))\
        .annotate(**annotations)\
        .values_list('date', *annotations.keys())\
        .order_by('date')


    end_date = timezone.now().date()
    start_date = end_date - timezone.timedelta(days=self_day)
    labels = [start_date + timezone.timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    return labels, requests, lambda request, point: point.strftime("%d-%m-%Y")

def _month_data(self_day, annotations, requests):
    requests = requests.annotate(date=models.functions.ExtractMonth('created_at'))\
                       .values('date')\
                       .annotate(**annotations)\
                       .values_list('date', *annotations.keys())\
                       .order_by('date')

    end_date = timezone.now().date()
    start_date = end_date - datetime.timedelta(days=self_day)

    labels = []
    for i in range(1, 13):
        month = start_date.month + i
        year = start_date.year
        if month > 12:
            month -= 12
            year += 1
        labels.append(month)

    return labels, requests, integer_to_month

class RequestFiltersModelMultipleChoceField(filters.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

class RequestFilterModelMultipleChoiceFilter(filters.ModelMultipleChoiceFilter):
    field_class = RequestFiltersModelMultipleChoceField

class FilteredRequestFilterSet(FilterSet):
    method = filters.ChoiceFilter(
        choices=FilterMethodChoices.choices,
        method='filter_method',
        label=_('Method'),
    )

    filter = filters.ChoiceFilter(
        choices=FilterChoices.choices,
        method='filter_filter',
        label=_('Filter Type'),
    )

    filters = RequestFilterModelMultipleChoiceFilter(
        queryset=Filter.objects.all(),
        method='filter_filters',
        label=_('Filters'),
    )

    class Meta:
        model = FilteredRequest
        fields = [
            'method',
            'filter',
            'filters',
        ]

    def filter_method(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(_filter__method=value)
    
    def filter_filter(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(_filter__filter_type=value)
    
    def filter_filters(self, queryset, name, value):
        if not value:
            return queryset
        
        values = [v.pk for v in value]
        q = models.Q(_filter__pk=values[0])
        for v in values[1:]:
            q |= models.Q(_filter__pk=v)
        return queryset.filter(q)

class FilteredRequestChartView(WagtailAdminTemplateMixin, TemplateView):
    template_name = 'request_filters/chart_view.html'
    page_title = _('Filters Chart')
    page_subtitle = _('Analyse your filters')
    header_icon = 'clipboard-list'
    _show_breadcrumbs = True
    days = {
        "day": 1,
        "week": 7,
        "month": 30,
        "year": 365,
    }
    filters = {
        "day": _hour_data,
        "week": _week_data,
        "month": _date_data,
        "year": _month_data,
    }

    @property
    def header_buttons(self):
        filters = ["day", "week", "month", "year"]
        buttons = []
        for i, filter in enumerate(filters):
            # data = self.request.GET.get('filter', None)
            # if filter == data:
            #     continue

            buttons.append(
                Button(
                    _(filter.capitalize()),
                    url=reverse('filter_chart_view') + f"?query_by={filter}",
                    priority=i,
                )
            )

        ret_buttons = [
            ButtonWithDropdown(
                _('Filter'),
                # icon_name='filter',
                buttons=buttons,
                priority=0,
            )
        ]

        if self.request.user.has_perms([
                    f"{FilteredRequest._meta.app_label}.change_{FilteredRequest._meta.model_name}"
                ]):
            ret_buttons.append(
                HeaderButton(
                    _('Logs'),
                    url=reverse('request_filters_log:list'),
                    icon_name='clipboard-list',
                    priority=10,
                )
            )

        return ret_buttons


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
        for action, __ in FilterActionChoices.choices:
            annotations[f'count_{action.lower()}'] = models.Count(
                '_filter',
                filter=models.Q(
                    _filter__action=action
                ),
            )

        filter = request.GET.get('query_by', 'day')
        try:
            self_day = self.days[filter]
            filter_fn = self.filters[filter]
        except KeyError:
            self_day = self.days['day']
            filter_fn = self.filters['day']


        qs = FilteredRequest.objects.all()\
            .filter(created_at__gte=timezone.now() - timezone.timedelta(days=self_day))

        dj_filter = FilteredRequestFilterSet(request.GET, queryset=qs, request=request)

        labels, qs, fmt = filter_fn(self_day, annotations, dj_filter.qs)

        datasets = []
        for i, (_, action) in enumerate(FilterActionChoices.choices):
            dataset = {'label': action, 'data': []}
            data_points = {request[0]: request[i + 1] for request in qs}

            for point in labels:
                dataset['data'].append({
                    'x': fmt(request, point),
                    'y': data_points.get(point, 0),
                })

            datasets.append(dataset)

        labels = [fmt(request, point) for point in labels]

        chart = {
            "datasets": datasets,
            "labels": labels,
        }
        return self.render_to_response(
            context=self.get_context_data(
                chart = chart,
                query_by = filter,
                filter = dj_filter,
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
