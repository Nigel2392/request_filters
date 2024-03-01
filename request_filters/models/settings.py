from django.db import models
from django.utils.translation import gettext_lazy as _
from django.apps import apps

from wagtail.contrib.settings.models import (
    BaseGenericSetting, 
    register_setting,
)
from wagtail.admin.panels import (
    HelpPanel,
    FieldPanel,
    FieldRowPanel,
    InlinePanel,
)
from modelcluster.models import ClusterableModel

from ..options import (
    RequestFilters,
)

from typing import TYPE_CHECKING
import urllib.parse

if TYPE_CHECKING:
    from .filters import Filter, FilterQuerySet

def _p(text: str, *args: str, end_line: bool = True) -> str:
    p = [
        text,
    ]
    p.extend(args)
    if end_line:
        p.append("<br/>")
    return " ".join(p)

def _a(href: str, text: str) -> str:
    if not text:
        parsed = urllib.parse.urlparse(href)
        text = parsed.netloc

    return f'<a href="{href}" target="_blank">{text}</a>'

def _l(texts: list[str], tag: str = "ol", sub_tag: str = "li") -> str:
    tags = "".join([f"<{sub_tag}>{text}</{sub_tag}>" for text in texts])
    return f"<{tag}>{tags}</{tag}>"



FilterModel: "Filter" = apps.get_model(
    "request_filters",
    "Filter",
    require_ready=False,
)


@register_setting(
    icon="key",
    name="request_filters_settings_disabled",
    order=1450,
)
class FilterSettings(ClusterableModel, BaseGenericSetting):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._filters = []

    filters: "FilterQuerySet"

    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Last Updated"),
        editable=False,
    )

    panels = [
        HelpPanel(_("".join([
            _p("This settings page allows you to configure filters for requests."),
            _p("Filters are used for:"),
            _l([
                "Blocking requests",
                "Allowing requests",
                "Redirecting requests",
                "Logging requests",
            ], "ol"),
            _p("Learn more about and test your ", _a("https://regexr.com/", "regex")),
            _p("Learn more about", _a("https://en.wikipedia.org/wiki/Glob_(programming)", "glob patterns")),
            _p("Learn about", _a("https://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing", "CIDR notation")),
        ]))),
        FieldPanel("last_updated", read_only=True),
        InlinePanel("filters", panels=[
            FieldRowPanel([
                    FieldPanel("filter_type"),
                    FieldPanel("method"),
                    FieldPanel("action"),
                    FieldPanel("active"),
                ]),
                FieldPanel("action_value"),
                FieldPanel("filter_value"),
            ], 
            label=_("Filters")
        ),
    ]

    class Meta:
        verbose_name = _("Request Filter Settings")
        verbose_name_plural = _("Request Filter Settings")

    def __str__(self):
        return f"{str(self._meta.verbose_name)} / {self.last_updated}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if RequestFilters.CLEAR_CACHE_ON_SAVE_SETTINGS:
            RequestFilters.cache_backend.delete(RequestFilters.SETTINGS_CACHE_KEY)
            RequestFilters.cache_backend.delete(RequestFilters.FILTERS_CACHE_KEY)

    def get_filters(self) -> list["Filter"]:
        if self._filters is None:
            self._filters = self.filters.all()
        return self._filters
    
    @classmethod
    def base_queryset(cls):
        return super()\
            .base_queryset()\
            .prefetch_related(models.Prefetch(
                "filters", 
                queryset=FilterModel.objects\
                    .active()\
                    .order_by("sort_order"),
            ))

    @classmethod
    def load_from_cache(cls, request_or_site=None):
        """
            Load the settings from the cache, 
            or fetch it from the database and cache it
        """

        attr_name = cls.get_cache_attr_name()
        if hasattr(request_or_site, attr_name):
            return getattr(request_or_site, attr_name)

        # Try to get the settings from the cache
        self = RequestFilters.cache_backend.get(RequestFilters.SETTINGS_CACHE_KEY, None)

        if self is None:
            # Load the settings from the database
            self = cls.load(request_or_site=request_or_site)
            
            # Cache the filters for the settings
            self._filters = self.filters.all()
            
            # Cache the settings
            RequestFilters.cache_backend.set(
                RequestFilters.SETTINGS_CACHE_KEY,
                self,
                RequestFilters.SETTINGS_CACHE_TIMEOUT.total_seconds(),
            )

        # Cache for next time.
        # This gets done in the load method, but does not include the filters
        setattr(request_or_site, attr_name, self)

        return self
    


