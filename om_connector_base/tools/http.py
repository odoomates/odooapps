import logging
import time

import requests

_logger = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}


def request_with_retry(method, url, *, session=None, retries=4, backoff=1.0, timeout=30, sleep=time.sleep, **kwargs):
    """ ``requests.request`` that waits and tries again on a rate limit (429), a server error (5xx)
    or a network error, up to ``retries`` times. The wait follows the ``Retry-After`` header when
    the server sends one, else doubles from ``backoff`` seconds.

    The last response is returned as is, whatever its status: the caller checks it.
    """
    http = session or requests
    for attempt in range(retries + 1):
        try:
            response = http.request(method, url, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
            wait = backoff * 2 ** attempt
            _logger.info("%s %s: network error, new try in %.1fs", method, url, wait)
        else:
            if response.status_code not in RETRY_STATUSES or attempt == retries:
                return response
            wait = _retry_after(response) or backoff * 2 ** attempt
            _logger.info("%s %s: HTTP %s, new try in %.1fs", method, url, response.status_code, wait)
        sleep(wait)


def _retry_after(response):
    try:
        return max(float(response.headers.get('Retry-After', '')), 0.0)
    except ValueError:
        return None
