import logging
from django.db import models
from django.conf import settings as django_settings
from django.core.exceptions import PermissionDenied
from django.http import (
    HttpRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.utils.translation import gettext_lazy as _
from django.utils.translation.trans_real import language_code_prefix_re
from django.utils.translation import get_language_from_path
from typing import TYPE_CHECKING

from . import log
from .util import (
    get_ip_address,
    skip_logging,
)
from .signals import (
    request_blocked,
    request_redirected,
)
from .options import (
    RequestFilters,
)

if TYPE_CHECKING:
    from .models import Filter, FilterSettings


def strip_language_from_path(path):
    # Get the language code from the path
    language_code = get_language_from_path(path)
    if language_code:
        # If the language code is found, remove it from the path
        path = language_code_prefix_re.sub("", path, 1)
    return path



class FilterActionChoices(models.TextChoices):
    ALLOW       = "ALLOW",      _("Allow")
    BLOCK       = "BLOCK",      _("Block")
    REDIRECT    = "REDIRECT",   _("Redirect")
    LOG         = "LOG",        _("Log")


def FILTER_ALLOWS_REQUEST(filter: "Filter", settings: "FilterSettings", request: HttpRequest, get_response):
    """
        Lets a request pass - skips any further filters and their checks.
        Filters in the list before this action will still be checked and acted upon.
    """
    ipaddr = get_ip_address(request)
    log(f"[Filter / {filter.action}] (LOG_TO_DATABASE: {RequestFilters.LOG_HAPPY_PATH}) Allowing request {ipaddr} with {filter}", logging.INFO)
    response = get_response(request)

    if not RequestFilters.LOG_HAPPY_PATH:
        response = skip_logging(response)

    return response

def FILTER_BLOCKS_REQUEST(filter: "Filter", settings: "FilterSettings", request: HttpRequest, get_response):
    """
        Blocks a request - does not execute any further filters or their checks.
    """

    # Requests don't get blocked for no reason - log with a reasonably high level.
    ipaddr = get_ip_address(request)
    log(f"[Filter / {filter.action}] Blocking request {ipaddr} with {filter}", logging.WARN)

    # Broadcast the request_blocked signal
    request_blocked.send(sender=filter, request=request, filter=filter)

    if request.accepts("application/json") and not request.accepts("text/*"):
        return JsonResponse({
            "error": RequestFilters.BLOCK_MESSAGE,
        }, status=403)

    raise PermissionDenied(RequestFilters.BLOCK_MESSAGE)
 

def FILTER_REDIRECTS_REQUEST(filter: "Filter", settings: "FilterSettings", request: HttpRequest, get_response):
    to = filter.action_value or "/"
    to = to.strip()
    
    ipaddr = get_ip_address(request)

    response = None
    if django_settings.USE_I18N:
        # If the path has a language prefix, strip it from the path
        cmp = strip_language_from_path(request.path)
        cmp = cmp.strip()
        if cmp == "":
            cmp = "/"

        if cmp and to == cmp:
            response = get_response(request)
    
    else:
        # If the path is the same as the redirect, return the response
        if to == request.path:
            response = get_response(request)
    

    if response is None:
        # Unsure about stability of redirects here - log INFO.
        log(f"[Filter / {filter.action}] Redirecting request {ipaddr} with {filter} from {request.path} to {to}", logging.INFO)
        response = HttpResponseRedirect(to)
    else:
        log(f"[Filter / {filter.action}] Request {ipaddr} with {filter} does not need redirection from {request.path} to {to}!", logging.DEBUG)

    # Broadcast the request_redirected signal
    request_redirected.send(sender=filter, request=request, filter=filter, response=response)

    return response

import json, logging
from urllib.parse import urlencode

def _FILTER_LOGS_REQUEST(log_level: int, allow_next_filter: bool = False):
    def _filter_logs_request(filter: "Filter", settings: "FilterSettings", request: HttpRequest, get_response):
        # Get the response and skip the logging in middleware 
        # to implement our custom logging here.
        response = get_response(request)
        _content_length = request.META.get('CONTENT_LENGTH', 0) or 0
        try:
            if int(_content_length) > 0:
                body = request.body
            else:
                body = None
        except (TypeError, ValueError):
            body = None

        ip_addr = get_ip_address(request)
        method = request.method
        path = request.path
        query = request.GET
        status_code = response.status_code

        meta = {k: v for k, v in request.headers.items()}
        meta_str = json.dumps(meta, indent=2, sort_keys=True)
        message = f"[Filter / {filter.action} / {ip_addr} / {method}: {status_code}] {path} {urlencode(query)}\nMETA:\n{meta_str}\n\nBODY:\n{body}\n"

        log(message, level=log_level)

        if allow_next_filter:
            return None
        
        return response

    return _filter_logs_request


FILTER_LOGS_REQUEST = _FILTER_LOGS_REQUEST(RequestFilters.FILTER_LOG_LEVEL, False)
FILTER_LOGS_REQUEST_ALLOW_NEXT = _FILTER_LOGS_REQUEST(RequestFilters.FILTER_LOG_LEVEL, True)


FILTER_ACTIONS = {
    FilterActionChoices.ALLOW:      FILTER_ALLOWS_REQUEST,
    FilterActionChoices.BLOCK:      FILTER_BLOCKS_REQUEST,
    FilterActionChoices.REDIRECT:   FILTER_REDIRECTS_REQUEST,
    FilterActionChoices.LOG:        FILTER_LOGS_REQUEST_ALLOW_NEXT,
}

