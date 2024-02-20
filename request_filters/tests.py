from django.test import TestCase
import ipaddress, random

from .models import (
    Filter,
    FilterChoices,
    FilterMethodChoices,
    FilterActionChoices,
)
from .util import ip_in_cidr


def generate_ips_for_test(cidr, inside_count, outside_count):
    network = ipaddress.ip_network(cidr)
    all_ips = list(network.hosts())

    # Select inside IPs
    inside_ips = random.sample(all_ips, min(inside_count, len(all_ips)))

    # Generate outside IPs
    outside_ips = []
    while len(outside_ips) < outside_count:
        random_ip = ipaddress.IPv4Address(random.randint(0, 2**32 - 1))
        if random_ip not in network:
            outside_ips.append(str(random_ip))

    # Prepare the dictionary for test cases
    test_ips = {
        'inside': [str(ip) for ip in inside_ips],
        'outside': outside_ips,
    }
    
    return test_ips

# Example CIDR ranges for testing
ranges = [
    "222.240.205.0/24",
    "185.76.203.0/24",
    "46.227.139.0/24",
    "21.133.158.0/24",
    "155.173.115.0/24",
]

user_agents = [
    "Googlebot",
    "Bingbot",
    "Yandexbot",
    "DuckDuckBot",
    "Baiduspider",
]

fail_agents = [
    "test",
    "debug",
    "password",
    "admin",
    "login",
    "logout",
]

paths = [
    "/admin",
    "/login",
    "/logout",
    "/register",
    "/password_reset",
    "/password_change",
    "/profile",
    "/settings",
]

fail_paths = [
    "/fail/admin",
    "/fail/login",
    "/fail/logout",
    "/fail/register",
    "/fail/password_reset",
    "/fail/password_change",
    "/fail/profile",
    "/fail/settings",
]

query_strings = [
    "test",
    "debug",
    "password",
    "admin",
    "login",
    "logout",
]

fail_query_strings = [
    "fail",
    "error",
    "exception",
    "warning",
    "critical",
]



class TestIPAddr(TestCase):
    def test_ip_in_cidr(self):
        for cidr in ranges:
            ips = generate_ips_for_test(cidr, 10, 10)
            for ip in ips['inside']:
                self.assertTrue(ip_in_cidr(ip, cidr))

            for ip in ips['outside']:
                self.assertFalse(ip_in_cidr(ip, cidr))


def get_response(request):
    return "SUCCESS_RESPONSE"

# from .middleware import RequestFilterMiddleware
# 
# class TestRequestFilterMiddleware(TestCase):
#     def test_request_filter_middleware(self):
#         middleware = RequestFilterMiddleware(get_response)
#         request = type("Request", (), {"META": {}})()
#         response = middleware(request)
#         self.assertEqual(response, "SUCCESS_RESPONSE")



filters = []

for cidr in ranges:
    filters.append(Filter(
        filter_type=FilterChoices.IP,
        method=FilterMethodChoices.ABSOLUTE,
        action=FilterActionChoices.BLOCK,
        filter_value=cidr,
    ))

filters += [
    Filter(
        filter_type=FilterChoices.IP,
        method=FilterMethodChoices.REGEX,
        action=FilterActionChoices.BLOCK,
        filter_value="\d+\.\d+\.\d+\.\d+",
    ),
]


# filters += Filter(
#     filter_type=FilterChoices.USER_AGENT,
#     method=FilterMethodChoices.ABSOLUTE,
#     action=FilterActionChoices.BLOCK,
#     filter_value="Googlebot",
# )
# 
# filters += Filter(
#     filter_type=FilterChoices.PATH,
#     method=FilterMethodChoices.ABSOLUTE,
#     action=FilterActionChoices.BLOCK,
#     filter_value="/admin",
# )
# 
# filters += Filter(
#     filter_type=FilterChoices.QUERY_STRING,
#     method=FilterMethodChoices.ABSOLUTE,
#     action=FilterActionChoices.BLOCK,
#     filter_value="test",
# )


class FakeRequest:
    META = {}
    path = "/test"
    GET = {}
    POST = {}
    COOKIES = {}
    FILES = {}

    def __init__(self, path=None, query_string=None, user_agent=None, ip=None):
        self.META['REMOTE_ADDR'] = ip
        self.META['HTTP_USER_AGENT'] = user_agent
        self.path = path
        self.GET = {"test": query_string}

    def __str__(self):
        return f"FakeRequest({self.META['REMOTE_ADDR']})"

def generate_random_ips(count):
    ips = []
    for _ in range(count):
        ip = ipaddress.IPv4Address(random.randint(0, 2**32 - 1))
        ips.append(str(ip))
    return ips

class TestFilter(TestCase):
    def test_filter(self):
        for filter in filters:
            filter: Filter
            if filter.filter_type == FilterChoices.IP:
                if filter.method == FilterMethodChoices.ABSOLUTE:
                    ips = generate_ips_for_test(filter.filter_value, 10, 10)

                    for ip in ips['inside']:
                        self.assertTrue(filter.passes_test(None, FakeRequest(ip=ip)), f"IP {ip} should pass for filter {filter.filter_value} ({filter.method})")

                    for ip in ips['outside']:
                        self.assertFalse(filter.passes_test(None, FakeRequest(ip=ip)), f"IP {ip} should not pass for filter {filter.filter_value} ({filter.method})")

                elif filter.method == FilterMethodChoices.REGEX:
                    ips = generate_random_ips(255 * 255)
                    for ip in ips:
                        self.assertTrue(filter.passes_test(None, FakeRequest(ip=ip)), f"IP {ip} should pass for filter {filter.filter_value} ({filter.method})")

