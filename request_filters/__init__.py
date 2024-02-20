default_app_config = "request_filters.apps.RequestFiltersConfig"

import logging as _logging
_logger = _logging.getLogger("request_filters")

# LOG_FORMAT = "%(asctime)s [%(levelname)s / %(name)s]: %(message)s"
def log(message, level=_logging.INFO, *args, **kwargs):
    s = f'[{_logging.getLevelName(level)} / {_logger.name}]: {message}'
    _logger.log(level, s, *args, **kwargs)

log.DEBUG = _logging.DEBUG
log.INFO = _logging.INFO
log.WARN = _logging.WARN
log.ERROR = _logging.ERROR
log.CRITICAL = _logging.CRITICAL

__version__ = '1.2.2'
VERSION = tuple(__version__.split("."))


