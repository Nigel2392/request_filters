import logging
from django.db import models
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from wagtail.admin.panels import (
    FieldPanel,
    FieldRowPanel,
)

from wagtail.models import Orderable
from modelcluster.fields import ParentalKey

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import FilterSettings

from ..options import (
    RequestFilters,
)
from ..actions import (
    FilterActionChoices,
    FILTER_ACTIONS,
)
from ..checks import (
    FilterChoices,
    FilterMethodChoices,
    FILTER_CHECKS,
)
from .. import log


class FilterQuerySet(models.QuerySet):

    def active(self):
        return self.filter(active=True)
    
    def for_settings(self, settings: "FilterSettings"):
        return self.filter(settings=settings)
    
    def from_cache(self):
        filters = RequestFilters.cache_backend.get(RequestFilters.FILTERS_CACHE_KEY)
        if filters is None:
            filters = list(self)
            RequestFilters.cache_backend.set(RequestFilters.FILTERS_CACHE_KEY, filters, RequestFilters.FILTERS_CACHE_TIMEOUT.total_seconds())
        return filters

    
            
class Filter(Orderable):

    settings = ParentalKey(
        "FilterSettings",
        related_name="filters",
        on_delete=models.CASCADE,
    )

    filter_type = models.CharField(
        max_length=20,
        choices=FilterChoices.choices,
        default=FilterChoices.IP,
        verbose_name=_("Filter Type"),
    )

    method = models.CharField(
        max_length=20,
        choices=FilterMethodChoices.choices,
        default=FilterMethodChoices.ABSOLUTE,
        verbose_name=_("Method"),
    )

    action = models.CharField(
        max_length=20,
        choices=FilterActionChoices.choices,
        default=FilterActionChoices.BLOCK,
        verbose_name=_("Action"),
    )

    action_value = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Action Value"),
        help_text=_("The value to use for the action. For example, if you are redirecting, you would enter the URL here."),
    )

    filter_value = models.CharField(
        max_length=255,
        verbose_name=_("Filter Value"),
        help_text=_(
            "The value to filter on. For example, if you are filtering on IP, you would enter an IP address or CIDR range here."
        ),
    )

    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )

    panels = [
        FieldRowPanel([
            FieldPanel("filter_type"),
            FieldPanel("method"),
            FieldPanel("action"),
            FieldPanel("active"),
        ]),
        FieldPanel("action_value"),
        FieldPanel("filter_value"),
    ]

    objects: FilterQuerySet = FilterQuerySet.as_manager()

    class Meta:
        verbose_name = _("Filter")
        verbose_name_plural = _("Filters")
        ordering = ["sort_order"]

    def __str__(self):
        if not self.active:
            return f"Filter({self.get_filter_type_display()} / INACTIVE)"
        s = [
            self.get_filter_type_display(),
            self.get_method_display(),
            self.get_action_display(),
            self.filter_value,
        ]
        s = " > ".join(s)
        s = s.upper()
        return f"Filter({s})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if RequestFilters.CLEAR_CACHE_ON_SAVE_FILTERS:
            RequestFilters.cache_backend.delete(RequestFilters.SETTINGS_CACHE_KEY)
            RequestFilters.cache_backend.delete(RequestFilters.FILTERS_CACHE_KEY)

    def passes_test(self, settings: "FilterSettings", request: HttpRequest) -> bool:
        try:
            passes_test = FILTER_CHECKS[self.method][self.filter_type]
            return passes_test(self, settings, request)
        
        except (KeyError, TypeError, ValueError):
            return RequestFilters.default_check_value(self, settings, request)

    def execute_action(self, settings: "FilterSettings", request: HttpRequest, get_response: callable):
        try:
            return FILTER_ACTIONS[self.action](self, settings, request, get_response)
        except (KeyError, TypeError, ValueError) as e:
            log(f"Error executing action on {request.path} with {self}", exc_info=e, level=logging.ERROR)
            return RequestFilters.default_action_value(self, settings, request, get_response)
        
