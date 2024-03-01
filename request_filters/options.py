import ipaddress
from typing import Union, TYPE_CHECKING
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest, HttpResponseForbidden
from django.core.cache import caches
from django.utils import timezone
import logging

if TYPE_CHECKING:
    from .models import (
        Filter,
        FilterSettings,
    )

import fnmatch, functools

from .util import (
    ip_in_cidr,
    get_ip_address,
)

_VAR = "REQUEST_FILTERS"

class RequestFilterOptions(object):
    # List of excluded apps, all requests to these apps will be allowed (If resolver_match is available).
    # !Exclusions should preferably happen via IP ranges or absolute IPs.
    EXCLUDED_APPS:                list[str] = [
        "admin",
    ]

    # Excluded paths, all requests to these paths will be allowed.
    # Paths should be in the format of a glob pattern.
    # !Exclusions should preferably happen via IP ranges or absolute IPs.
    EXCLUDED_PATHS:               list[str] = [
        "/admin/*",
        f"{getattr(settings, 'STATIC_URL', '/static/')}*",
        f"{getattr(settings, 'MEDIA_URL', '/media/')}*",
    ]

    # Excluded IP addresses, all requests from these IPs will be allowed.
    # This is the safest way to exclude requests from being filtered.
    EXCLUDED_IPS:                 list[str] = [
        "127.0.0.0/8", "::1/128",
    ]
    # Default cache backend to use for storing settings and filters
    CACHE_BACKEND:                str                   = "default"
    BLOCK_MESSAGE:                str                   = _("You are not allowed to access this resource")
    SETTINGS_CACHE_KEY:           str                   = "request_filters_settings"
    FILTERS_CACHE_KEY:            str                   = "request_filters_filters"
    SETTINGS_CACHE_TIMEOUT:       timezone.timedelta    = timezone.timedelta(minutes=5) # timezone.timedelta(seconds=5) # timezone.timedelta(minutes=5)
    FILTERS_CACHE_TIMEOUT:        timezone.timedelta    = timezone.timedelta(hours=1)   # timezone.timedelta(seconds=5) # timezone.timedelta(hours=1)
    CLEAR_CACHE_ON_SAVE_SETTINGS: bool                  = True  # Clear cache when settings are saved
    CLEAR_CACHE_ON_SAVE_FILTERS:  bool                  = True  # Clear cache when filters are saved
    ADD_FILTER_HEADERS:           bool                  = True  # Add headers to the response which displays minimal information about the filters.
    LOG_HAPPY_PATH:               bool                  = False # Log requests that are allowed by the filters
    LOG_ALLOWED_REQUESTS:         bool                  = True  # Log requests that are allowed by the filters
    DEFAULT_CHECK_VALUE:          Union[bool, callable] = True  # Allow checks to pass by default
    DEFAULT_ACTION_VALUE:         callable              = lambda self, filter, settings, request, get_response: HttpResponseForbidden(
        _("You are not allowed to access this resource")
    )
    REGISTER_TO_MENU:             str                   = "register_settings_menu_item" # The name of the hook to register the menu item to.
    FILTER_LOG_LEVEL:             int                   = logging.INFO # The log level to use for filter logs.

    def __init__(self):
        for i, ip in enumerate(self.EXCLUDED_IPS):
            if "/" in ip:
                addr = ipaddress.ip_network(ip, strict=False)
            else:
                addr = ipaddress.ip_address(ip)

            self.EXCLUDED_IPS[i] = addr


    def __getattribute__(self, name):
        return getattr(
            settings,
            f"{_VAR}_{name}",
            object.__getattribute__(self, name),
        )

    
    def default_check_value(self, filter: "Filter", settings: "FilterSettings", request: HttpRequest):
        """
            Default value I.E. when a check cannot be performed
        """
        if callable(self.DEFAULT_CHECK_VALUE):
            return self.DEFAULT_CHECK_VALUE(filter, settings, request)
        return self.DEFAULT_CHECK_VALUE
    
    def default_action_value(self, filter: "Filter", settings: "FilterSettings", request: HttpRequest, get_response: callable):
        """
            Default action to perform when a filter matches
        """
        return self.DEFAULT_ACTION_VALUE(filter, settings, request, get_response)

    @property
    def cache_backend(self):
        """
            Return the default cache backend for the settings and filters
        """
        return caches[self.CACHE_BACKEND]

    def request_is_excluded(self, request: HttpRequest):
        """
            Check if a request should be excluded from filtering
        """
        checks = [
            self.ip_is_excluded(
                get_ip_address(request),
            ),
            self.path_is_excluded(request.path),
        ]
        if request.resolver_match:
            checks.append(
                self.app_is_excluded(request.resolver_match.app_name)
            )

        return any(checks)
    
    def app_is_excluded(self, app_name):
        """
            Check if an app is excluded from filtering.
        """
        return app_name.lower() in self.EXCLUDED_APPS
    
    @functools.lru_cache(maxsize=128)
    def path_is_excluded(self, path):
        """
            Check if a path is excluded from filtering.
        """
        for p in self.EXCLUDED_PATHS:
            if fnmatch.fnmatch(path, p):
                return True
        return False

    @functools.lru_cache(maxsize=128)
    def ip_is_excluded(self, ip):
        """
            Check if an IP is excluded from filtering by cidr range or absolute match.
        """
        for excluded_ip in self.EXCLUDED_IPS:
            if ip_in_cidr(ip, excluded_ip):
                return True

        return False
    

# Default options for the request_filters app.
# 
# These can be overridden by settings.
# 
# Example:
#
#  REQUEST_FILTERS = {
#   "EXCLUDED_APPS": ["admin"],
#   ...
# }
#
RequestFilters = RequestFilterOptions()

del RequestFilterOptions
