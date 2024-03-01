from typing import Literal, Union
from django.conf import settings
from django.contrib.gis.geoip2 import (
    GeoIP2,
)

import ipaddress, functools

IS_PROXIED = getattr(settings, "USE_X_FORWARDED_HOST", False)
GEO_IP = GeoIP2()


def get_ip_address(request):
    if IS_PROXIED:
        addr = request.META.get('HTTP_X_FORWARDED_FOR', None)
        if addr:
            return addr.split(',')[-1].strip()
    else:
        return request.META.get('REMOTE_ADDR', None)

def get_user_agent(request):
    return request.META.get('HTTP_USER_AGENT', "")

def get_referer(request):
    return request.META.get('HTTP_REFERER', "")

@functools.lru_cache(maxsize=128)
def ip_in_cidr(ip, cidr):
    if not isinstance(ip, ipaddress.IPv4Address) and not isinstance(ip, ipaddress.IPv6Address):
        ip = ipaddress.ip_address(ip)
        
    if isinstance(cidr, str):
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    elif isinstance(cidr, ipaddress.IPv4Network) or isinstance(cidr, ipaddress.IPv6Network):
        return ipaddress.ip_address(ip) in cidr
    elif not (
        isinstance(cidr, ipaddress.IPv4Address) and isinstance(cidr, ipaddress.IPv6Address)
    ):
        cidr = ipaddress.ip_address(cidr)

    if ip == cidr:
        return True

    return False


@functools.lru_cache(maxsize=128)
def get_country(ip) -> dict[Union[Literal["country_code"], Literal["country_name"]], str]:
    return GEO_IP.country(ip)

def skip_logging(request_or_response, skip: bool = True):
    """
        Mark a response or request.
        It will not be logged to the database.
    """
    setattr(request_or_response, "filters_skip_logging", skip)
    return request_or_response

def logging_skipped(request_or_response):
    """
        Check if a request or response has been marked as logging skipped.
    """
    return hasattr(request_or_response, "filters_skip_logging") and request_or_response.filters_skip_logging

