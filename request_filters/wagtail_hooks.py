from typing import Any
from django import forms
from django.db import models
from django.utils import timezone
from django.urls import path, reverse
from django.views.generic import TemplateView
from django.utils.translation import gettext_lazy as _, gettext_lazy
from django.http import HttpRequest, HttpResponse

from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, IndexView
from wagtail.admin.views.generic import WagtailAdminTemplateMixin
from wagtail.admin.widgets.button import Button, ButtonWithDropdown, HeaderButton
from wagtail import hooks

from django_filters.filterset import FilterSet
from django_filters import filters

from .checks import FilterChoices, FilterMethodChoices
from .models import FilteredRequest, FilterSettings, Filter, FilterActionChoices
from .options import RequestFilters

class LogIndexView(IndexView):
    def get_paginate_by(self, queryset):
        return 50

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

    index_view_class = LogIndexView

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


def day_to_weekday(point):
    return weekdays[point.isoweekday()]


def integer_to_month(point):
    return months[point.month]


def _hour_data(annotations, qs, from_date: timezone.datetime, to_date: timezone.datetime):
    qs = qs.values(date=models.functions.TruncHour("created_at"))\
        .annotate(**annotations)\
        .values_list('date', *annotations.keys())\
        .order_by('date')
    
    hour_start = from_date.replace(minute=0, second=0, microsecond=0)
    hour_end = to_date.replace(minute=0, second=0, microsecond=0)

    labels = []
    while hour_start <= hour_end:
        labels.append(hour_start)
        hour_start = hour_start + timezone.timedelta(hours=1)

    return labels, qs, lambda point: point.strftime("%H:%M")


def _week_data(annotations, qs, from_date: timezone.datetime, to_date: timezone.datetime):
    qs = qs.values(date=models.functions.TruncDate("created_at"))\
        .annotate(**annotations)\
        .values_list('date', *annotations.keys())\
        .order_by('date')

    from_date = from_date.date()
    to_date = to_date.date()

    labels = []
    while from_date <= to_date:
        labels.append(from_date)
        from_date = from_date + timezone.timedelta(days=1)

    return labels, qs, day_to_weekday


def _date_data(annotations, qs, from_date: timezone.datetime, to_date: timezone.datetime):
    qs = qs.values(date=models.functions.TruncDate("created_at"))\
        .annotate(**annotations)\
        .values_list('date', *annotations.keys())\
        .order_by('date')
    
    from_date = from_date.date()
    to_date = to_date.date()

    labels = []
    while from_date <= to_date:
        labels.append(from_date)
        from_date = from_date + timezone.timedelta(days=1)

    return labels, qs, lambda point: point.strftime("%d-%m-%Y")


def _month_data(annotations, qs, from_date: timezone.datetime, to_date: timezone.datetime):
    qs = qs.annotate(date=models.functions.TruncMonth("created_at", output_field=models.DateField()))\
                       .values('date')\
                       .annotate(**annotations)\
                       .values_list('date', *annotations.keys())\
                       .order_by('date')

    start_date = from_date.date().replace(day=1)
    end_date = to_date.date().replace(day=1)

    labels = []
    while start_date <= end_date:
        labels.append(start_date)
        if start_date.month == 12:
            start_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            start_date = start_date.replace(month=start_date.month + 1)
        
    return labels, qs, lambda point: point.strftime("%m-%Y")

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

    chart_type = filters.ChoiceFilter(
        choices=[
            ('line', _('Line')),
            ('bar', _('Bar')),
        ],
        label=_('Chart Type'),
        empty_label=None,
        initial='line',
        method='filter_chart_type',
    )

    from_date = filters.DateTimeFilter(
        field_name='created_at',
        label=_('From Date'),
        method='filter_from_date',
    )

    to_date = filters.DateTimeFilter(
        field_name='created_at',
        label=_('To Date'),
        method='filter_to_date',
    )

    filters = RequestFilterModelMultipleChoiceFilter(
        queryset=Filter.objects.all(),
        method='filter_filters',
        label=_('Filters'),
    )

    def __init__(self, *args, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.form.fields['chart_type'].initial = 'line'

    class Meta:
        model = FilteredRequest
        fields = [
            'method',
            'filter',
            'chart_type',
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
        
    def filter_chart_type(self, queryset, name, value):
        return queryset
    
    def filter_to_date(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(created_at__lte=value)
    
    def filter_from_date(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(created_at__gte=value)

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

        query = self.request.GET.copy()
        query.pop('query_by', None)

        for i, filter in enumerate(filters):
            # data = self.request.GET.get('filter', None)
            # if filter == data:
            #     continue

            url =  f"{reverse('filter_chart_view')}?query_by={filter}"
            if query:
                url += f"&{query.urlencode()}"

            buttons.append(
                Button(
                    _(filter.capitalize()),
                    url=url,
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
        dj_filter = FilteredRequestFilterSet(request.GET, queryset=FilteredRequest.objects.all(), request=request)
        qs = dj_filter.qs

        to_date = getattr(dj_filter.form, "cleaned_data", {}).get("to_date")
        from_date = getattr(dj_filter.form, "cleaned_data", {}).get("from_date")

        if from_date and to_date:
            delta_from_to = to_date - from_date
            if delta_from_to.days > 365:
                delta = "year"
            elif delta_from_to.days >= 30:
                delta = "month"
            elif delta_from_to.days > 7:
                delta = "month"
            elif delta_from_to.days > 1:
                delta = "week"
            elif delta_from_to.days <= 1:
                delta = "day"
            filter_fn = self.filters[delta]
        else:
            try: 
                filter_fn = self.filters[filter]
            except KeyError: 
                filter = "day"
                filter_fn = self.filters['day']
            
            if to_date is None or from_date is None:
                to_date = timezone.now()
                from_date = to_date - timezone.timedelta(days=self.days[filter])
        

        labels, qs, fmt = filter_fn(annotations, qs, from_date, to_date)

        datasets = []
        for i, (_, action) in enumerate(FilterActionChoices.choices):
            dataset = {'label': action, 'data': []}
            data_points = {request[0]: request[i + 1] for request in qs}

            for point in labels:
                dataset['data'].append({
                    'x': fmt(point),
                    'y': data_points.get(point, 0),
                })

            datasets.append(dataset)

        labels = [fmt(point) for point in labels]

        chart = {
            "datasets": datasets,
            "labels": labels,
        }
        return self.render_to_response(
            context=self.get_context_data(
                chart = chart,
                query_by = filter,
                filter = dj_filter,
                chart_type = dj_filter.form.cleaned_data.get('chart_type', 'line'),
            ),
        )
    
    def filter_by_allow(self, value):
        return models.Q(_filter__action=value)
    
    def filter_by_block(self, value):
        return models.Q(_filter__action=value)
    
    def filter_by_redirect(self, value):
        return models.Q(_filter__action=value)
    
    def filter_by_log(self, value):
        return models.Q(_filter__action=value)
    

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
