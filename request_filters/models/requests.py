import logging, ipaddress
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.conf import settings as django_settings
from django.utils.translation import (
    gettext_lazy as _,
    get_language_from_request,
)

from geoip2.errors import AddressNotFoundError
from django.contrib.gis.geoip2 import (
    GeoIP2Exception,
)

from .filters import Filter
from ..util import (
    get_ip_address,
    get_country,
    logging_skipped,
    skip_logging,
)

from .. import log

from wagtail.admin.panels import (
    FieldPanel,
    FieldRowPanel,
    ObjectList,
    TabbedInterface,
)


class LogFailed(Exception):
    pass


class FilteredRequest(models.Model):
    """
        A FilteredRequest is a request that has failed a filter check.
    """
    filter_index = models.PositiveIntegerField(
        verbose_name=_("Filter Index"),
        help_text=_("The index of the filter that was triggered."),
        blank=True,
        null=True,
    )
    _filter = models.JSONField(
        verbose_name=_("Filter"),
        help_text=_("The filter that was triggered."),
        blank=True,
        null=False,
        default=dict,
    )

    request_path = models.CharField(
        max_length=255,
        verbose_name=_("Request Path"),
        help_text=_("The path of the request that was filtered."),
    )

    request_method = models.CharField(
        max_length=10,
        verbose_name=_("Request Method"),
        help_text=_("The method of the request that was filtered."),
    )

    request_ip = models.GenericIPAddressField(
        verbose_name=_("Request IP"),
        help_text=_("The IP of the request that was filtered."),
    )

    request_language = models.CharField(
        max_length=10,
        verbose_name=_("Request Language"),
        help_text=_("The language of the request that was filtered."),
    )

    request_is_secure = models.BooleanField(
        verbose_name=_("Request Is Secure"),
        help_text=_("Whether the request was secure."),
    )

    response_info = models.JSONField(
        verbose_name=_("Response Info"),
        help_text=_("Extra information about the response after the request was filtered."),
        blank=True,
        null=False,
        default=dict,
    )

    request_info = models.JSONField(
        verbose_name=_("Request Info"),
        help_text=_("Extra information about the request that was filtered."),
        blank=True,
        null=False,
        default=dict,
    )

    gis_data = models.JSONField(
        verbose_name=_("GIS Data"),
        help_text=_("The GIS data of the request that was filtered."),
        blank=True,
        null=False,
        default=dict,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At"),
    )

    main_panels = [
        FieldRowPanel([
            FieldPanel("request_method", read_only=True),
            FieldPanel("request_path", read_only=True),
        ]),
        FieldPanel("request_ip", read_only=True),
        FieldPanel("created_at", read_only=True),
        FieldPanel("gis_data", read_only=True),
    ]

    req_resp_panels = [
        FieldRowPanel([
            FieldPanel("request_language", read_only=True),
            FieldPanel("request_is_secure", read_only=True),
        ]),
        FieldPanel("response_info", read_only=True),
        FieldPanel("request_info", read_only=True),
    ]

    filter_panels = [
        FieldPanel("filter_index", read_only=True),
        FieldPanel("_filter", read_only=True),
    ]

    edit_handler = TabbedInterface([
        ObjectList(main_panels, heading=_("Main")),
        ObjectList(req_resp_panels, heading=_("Request/Response")),
        ObjectList(filter_panels, heading=_("Filter")),
    ])

    class Meta:
        verbose_name = _("Filtered Request")
        verbose_name_plural = _("Filtered Requests")
        ordering = ["-created_at__date", "-created_at__time__hour", "-created_at__time__minute", "-created_at__time__second", "filter_index"]
        permissions = (
            ("see_chart", _("View Chart")),
        )

    def __str__(self):

        s = []

        if self._filter:
            s.append(self.filter.get_action_display())

        s.append(self.request_ip)
        s.append(self.request_method)

        if self.request_language:
            s.append(self.request_language)

        if self.gis_data:
            n = self.gis_data.get("country_name", "")
            if n: s.append(n)

        if not self.pk:
            return f"FilteredRequest({'/'.join(s)})"

        return f"FilteredRequest({self.pk}: {'/'.join(s)})"
    
    def get_request_is_secure_display(self):
        return _("Secure") if self.request_is_secure else _("Insecure")

    def get_list_title(self):

        if self._filter:
            return f"{self.filter.get_filter_type_display()} ({self.request_method}/{self.request_ip})"

        if self.gis_data.get("country_name", self.request_language):
            return f"({self.request_ip}) {self.request_path}"

        if self.response_info:
            code = self.response_info.get("STATUS_CODE", "???") 
            return f"[{code}] {self.get_request_is_secure_display()}"
        
        return f"{self.request_method} {self.request_path}"
    get_list_title.short_description = _("Title")


    def get_list_description(self):
        if self._filter:
            filter = Filter(**self._filter)
            if self.filter.action_value:
                return f"{filter.get_action_display()} ({self.filter.action_value})"
            return f"{filter.get_action_display()}"

        return self.gis_data.get("country_name", self.request_language)
    get_list_description.short_description = _("Description")

    def get_match_performed(self):
        if self._filter:
            filter = Filter(**self._filter)
            return f"{filter.get_method_display()} ({filter.filter_value})"
        
        return str(_("PASSED"))
    get_match_performed.short_description = _("Match")

    @property
    def filter(self):
        return Filter(**self._filter)
    
    @classmethod
    def skip_logging(cls, request_or_response):
        """
            Note that the log action should stop if the req/res is skipped
        """
        return skip_logging(request_or_response)
    
    @classmethod
    def should_log(cls, request_or_response):
        """
            Check if the request or response should be logged
        """
        return not logging_skipped(request_or_response)

    @classmethod
    def log_request(cls, request: HttpRequest, filter: "Filter", response: HttpResponse = None, fail_silently: bool = False, filter_index = None, commit: bool = True):
        """
            Log a request that has been filtered
            if commit is False, returns a dictionary of kwargs to be used to create a FilteredRequest instance.
            If commit is True, the FilteredRequest instance will be created and saved to the database; the instance will be returned.
        """

        if not cls.should_log(request):
            log(f"({cls.__name__}) Request {request} has been skipped from logging.", level=logging.DEBUG)
            return
        
        if response and not cls.should_log(response):
            log(f"({cls.__name__}) Response {response} has been skipped from logging.", level=logging.DEBUG)
            return

        ip = get_ip_address(request)
        if not ip:
            log(f"({cls.__name__}) Could not get the IP address from the request ([{request.method}] - {request.path}).", level=logging.ERROR)
            if not fail_silently:
                raise LogFailed(f"Could not get the IP address from the request.")

        ipaddr = ipaddress.ip_address(ip)
        country = {}
        if not (ipaddr.is_private or ipaddr.is_reserved):
            try:
                country = get_country(ip)
            except (TypeError, ValueError, GeoIP2Exception, AddressNotFoundError):
                log(f"({cls.__name__}) Could not get the country information for IP address ([{ip}/{request.method}] - {request.path}).", level=logging.ERROR)
        else:
            country = {"country_code": "LOCAL", "country_name": "Local"}
        
        data = {
            "GET":          request.GET,
            "POST":         request.POST,
            "HAS_FILES":    bool(request.FILES),
            "HEADERS":      dict(request.headers),
        }

        _create_kwargs = {}

        if filter:
            if not filter.pk:
                err = f"Filter {filter} has not been saved for ([{ip}/{request.method}] - {request.path}])."
                log(f"({cls.__name__}) {err}", level=logging.ERROR)
                if not fail_silently:
                    raise LogFailed(err)

            _create_kwargs["_filter"] = {
                "pk":           filter.pk,
                "settings_id":  filter.settings_id,
                "filter_type":  filter.filter_type,
                "method":       filter.method,
                "action":       filter.action,
                "action_value": filter.action_value,
                "filter_value": filter.filter_value,
                "active":       filter.active,
            }

        if response:
            _create_kwargs["response_info"] = {
                "STATUS_CODE": response.status_code,
                "HEADERS":     dict(response.items()),
            }

        if django_settings.USE_I18N:
            _create_kwargs["request_language"] = get_language_from_request(request)

        _create_kwargs.update({
            "filter_index":     filter_index,
            "request_ip":       ip,
            "request_path":     request.path,
            "request_method":   request.method,
            "request_is_secure": request.is_secure(),
            "request_info":     data,
            "gis_data":         country,
        })

        if commit:
            self = cls(**_create_kwargs)
            log(f"({cls.__name__}) Logging filtered request {self} with {filter} ([{ip}/{request.method}] - {request.path}).", level=logging.DEBUG)
            self.save()

        return _create_kwargs
    
