from django.dispatch import Signal

request_started = Signal()
request_finished = Signal()
request_blocked = Signal()
request_redirected = Signal()



