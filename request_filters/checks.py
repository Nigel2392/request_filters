from django.db import models
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from django.contrib.gis.geoip2 import (
    GeoIP2Exception,
)
from .options import (
    RequestFilters,
)
from .util import (
    get_ip_address,
    ip_in_cidr,
    get_country,
)
from typing import TYPE_CHECKING, Callable
import re, fnmatch, ipaddress

if TYPE_CHECKING:
    from .models import FilterSettings, Filter

# yeah naming kinda sucks.
_py_filter = filter

class FilterChoices(models.TextChoices):
    IP              = "IP",             _("IP")
    USER_AGENT      = "USER_AGENT",     _("User Agent")
    PATH            = "PATH",           _("Path")
    QUERY_STRING    = "QUERY_STRING",   _("Query String")
    REFERER         = "REFERER",        _("Referer")
    COUNTRY         = "COUNTRY",        _("Country")
    METHOD          = "METHOD",         _("Method")

class FilterMethodChoices(models.TextChoices):
    ABSOLUTE = "ABSOLUTE",  _("Absolute")
    WILDCARD = "WILDCARD",  _("Wildcard")
    REGEX    = "REGEX",     _("Regex")
    IN       = "IN",        _("In")


"""
    Absolute checks
"""

def ABSOLUTE_FILTER_CHECK_IP(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    ip = get_ip_address(request)
    try:
        return ip_in_cidr(ip, filter.filter_value)
    except ValueError:
        return RequestFilters.default_check_value(filter, settings, request)
    
def ABSOLUTE_FILTER_CHECK_USER_AGENT(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    # The only absolute check that checks for inclusion.
    # The user agent can wildly vary.
    return filter.filter_value in request.META.get("HTTP_USER_AGENT", "") or\
            filter.filter_value == request.META.get("HTTP_USER_AGENT", "")

def ABSOLUTE_FILTER_CHECK_PATH(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return request.path.lower() == filter.filter_value.lower()

def ABSOLUTE_FILTER_CHECK_QUERY_STRING(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return filter.action_value == request.GET.get(filter.filter_value, "")

def ABSOLUTE_FILTER_CHECK_REFERER(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return filter.filter_value == request.META.get("HTTP_REFERER", "")

def ABSOLUTE_FILTER_CHECK_COUNTRY(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    ip = get_ip_address(request)
    ipaddr = ipaddress.ip_address(ip)
    if ipaddr.is_private or ipaddr.is_reserved:
        return False

    try:
        country = get_country(ip)
    except (TypeError, ValueError, GeoIP2Exception):
        return RequestFilters.default_check_value(filter, settings, request)
    
    code = country.get("country_code", "")
    name = country.get("country_name", "")

    return filter.filter_value in (code, name)

def ABSOLUTE_FILTER_CHECK_METHOD(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return filter.filter_value == request.method

"""
    Contains checks
"""

IN_FILTER_CHECK_IP = ABSOLUTE_FILTER_CHECK_IP


def IN_FILTER_CHECK_QUERY_STRING(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    values = list(_py_filter(lambda x: x.strip(), filter.filter_value.split(",")))
    actions = list(_py_filter(lambda x: x.strip(), filter.action_value.split(",")))
    if len(values) != len(actions):
        for value in values:
            if value in request.GET and request.GET.get(value, "") in actions:
                return True
        return False
    
    return any(request.GET.get(value, "") in actions for value in values)

def IN_FILTER_CHECK_COUNTRY(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    ip = get_ip_address(request)
    ipaddr = ipaddress.ip_address(ip)
    if ipaddr.is_private or ipaddr.is_reserved:
        return False

    try:
        country = get_country(ip)
    except (TypeError, ValueError, GeoIP2Exception):
        return RequestFilters.default_check_value(filter, settings, request)
    
    code = country.get("country_code", "")
    name = country.get("country_name", "")

    return any(filter_value in (code, name) for filter_value in filter.filter_value.split(","))

def IN_FILTER_CHECK_METHOD(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return request.method in filter.filter_value.split(",")

"""
    Regular expression checks
"""

def CHECK_GET_IP_ADDRESS(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return get_ip_address(request)

def CHECK_GET_USER_AGENT(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return request.META.get("HTTP_USER_AGENT", "")

def CHECK_GET_PATH(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return request.path

def CHECK_GET_QUERY_STRING(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return request.GET.get(filter.filter_value, "")

def CHECK_GET_REFERER(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return request.META.get("HTTP_REFERER", "")

def CHECK_GET_COUNTRY(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    ip = get_ip_address(request)
    ipaddr = ipaddress.ip_address(ip)
    if ipaddr.is_private or ipaddr.is_reserved:
        return "LOCAL"

    try:
        country = get_country(ip)
    except (TypeError, ValueError, GeoIP2Exception):
        raise ValueError("Could not get country information for IP address")
    
    return country.get("country_code", "")

def CHECK_GET_METHOD(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
    return request.method


def RE_MATCH_CHECK(get_value: Callable[["Filter", "FilterSettings", HttpRequest], str]):
    def _inner(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
        value = get_value(filter, settings, request)
        match = re.match(filter.filter_value, value)
        return bool(match)
    return _inner


def WC_MATCH_CHECK(get_value: Callable[["Filter", "FilterSettings", HttpRequest], str]):
    def _inner(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
        value = get_value(filter, settings, request)
        return fnmatch.fnmatch(value, filter.filter_value)
    return _inner


def IN_MATCH_CHECK(get_value: Callable[["Filter", "FilterSettings", HttpRequest], str], *process: Callable[[str], str], split_by = ","):
    def _inner(filter: "Filter", settings: "FilterSettings", request: HttpRequest):
        value = get_value(filter, settings, request)
        if isinstance(value, str):
            value = [value]

        if not filter.filter_value:
            # Special case.
            return False

        filter_value = filter.filter_value
        for p in process:
            filter_value = p(filter_value)

        if not split_by:
            return filter_value in value

        split = _s_str(filter_value, split_by)
        for val in value:
            if any(v in val for v in split):
                return True
            
        return False

    return _inner

def _p_upper(s):
    return s.upper()

def _s_str(s, split_by = ","):
    if not s:
        return [s]
    return list(_py_filter(lambda x: x.strip(), s.split(split_by)))

# Filters that are absolute and do not require any additional checks
FILTER_CHECKS_ABSOLUTE = {
    FilterChoices.IP:              ABSOLUTE_FILTER_CHECK_IP,
    FilterChoices.USER_AGENT:      ABSOLUTE_FILTER_CHECK_USER_AGENT,
    FilterChoices.PATH:            ABSOLUTE_FILTER_CHECK_PATH,
    FilterChoices.QUERY_STRING:    ABSOLUTE_FILTER_CHECK_QUERY_STRING,
    FilterChoices.REFERER:         ABSOLUTE_FILTER_CHECK_REFERER,
    FilterChoices.COUNTRY:         ABSOLUTE_FILTER_CHECK_COUNTRY,
    FilterChoices.METHOD:          ABSOLUTE_FILTER_CHECK_METHOD,
}

FILTER_CHECKS_RE = {
    FilterChoices.IP:              RE_MATCH_CHECK(CHECK_GET_IP_ADDRESS),
    FilterChoices.USER_AGENT:      RE_MATCH_CHECK(CHECK_GET_USER_AGENT),
    FilterChoices.PATH:            RE_MATCH_CHECK(CHECK_GET_PATH),
    FilterChoices.QUERY_STRING:    RE_MATCH_CHECK(CHECK_GET_QUERY_STRING),
    FilterChoices.REFERER:         RE_MATCH_CHECK(CHECK_GET_REFERER),
    FilterChoices.COUNTRY:         RE_MATCH_CHECK(CHECK_GET_COUNTRY),
    FilterChoices.METHOD:          RE_MATCH_CHECK(CHECK_GET_METHOD),
}


FILTER_CHECKS_WC = {
    FilterChoices.IP:              WC_MATCH_CHECK(CHECK_GET_IP_ADDRESS),
    FilterChoices.USER_AGENT:      WC_MATCH_CHECK(CHECK_GET_USER_AGENT),
    FilterChoices.PATH:            WC_MATCH_CHECK(CHECK_GET_PATH),
    FilterChoices.QUERY_STRING:    WC_MATCH_CHECK(CHECK_GET_QUERY_STRING),
    FilterChoices.REFERER:         WC_MATCH_CHECK(CHECK_GET_REFERER),
    FilterChoices.COUNTRY:         WC_MATCH_CHECK(CHECK_GET_COUNTRY),
    FilterChoices.METHOD:          WC_MATCH_CHECK(CHECK_GET_METHOD),
}

FILTER_CHECKS_IN = {
    FilterChoices.IP:              IN_FILTER_CHECK_IP,
    FilterChoices.USER_AGENT:      IN_MATCH_CHECK(CHECK_GET_USER_AGENT, split_by = None),
    FilterChoices.PATH:            IN_MATCH_CHECK(CHECK_GET_PATH, split_by = None),
    FilterChoices.QUERY_STRING:    IN_FILTER_CHECK_QUERY_STRING,
    FilterChoices.REFERER:         IN_MATCH_CHECK(CHECK_GET_REFERER, split_by = None),
    FilterChoices.COUNTRY:         IN_FILTER_CHECK_COUNTRY,
    FilterChoices.METHOD:          IN_MATCH_CHECK(CHECK_GET_METHOD, _p_upper, split_by = " "),
}

FILTER_CHECKS = {
    FilterMethodChoices.ABSOLUTE: FILTER_CHECKS_ABSOLUTE,
    FilterMethodChoices.IN:       FILTER_CHECKS_IN,
    FilterMethodChoices.REGEX:    FILTER_CHECKS_RE,
    FilterMethodChoices.WILDCARD: FILTER_CHECKS_WC,
}


