""" A small client of the WooCommerce REST API (wc/v3). """
import logging
import re

from odoo.exceptions import UserError

from odoo.addons.om_connector_base.tools import request_with_retry

_logger = logging.getLogger(__name__)

API_PATH = 'wc/v3'
PAGE_SIZE = 100
BATCH_SIZE = 100


class WooError(Exception):
    """ An error of the WooCommerce site that may pass if the call is made again later. """


class WooUserError(UserError):
    """ WooCommerce refused the call: making it again gives the same error. """


class WooAuthError(UserError):
    """ The consumer key or secret is wrong, or lacks the read/write permission. """


def normalize_site_url(value):
    """ ``My-Shop.com/`` → ``https://my-shop.com``; keeps a sub-folder (``https://example.com/shop``). """
    value = (value or '').strip()
    if not value:
        return value
    if not re.match(r'^https?://', value, re.I):
        value = 'https://' + value
    scheme, rest = value.split('://', 1)
    host, _sep, path = rest.partition('/')
    path = path.split('?')[0].split('#')[0].strip('/')
    for suffix in ('wp-admin', 'wp-json'):
        if path == suffix or path.endswith('/' + suffix):
            path = path[:-len(suffix)].strip('/')
    return f"{scheme.lower()}://{host.lower()}" + (f'/{path}' if path else '')


class WooClient:
    """ Calls the REST API of one WooCommerce site with a consumer key and secret.

    The key and secret go in an HTTP Basic header, or in the query string when ``query_auth`` is
    set (for the servers that drop the Authorization header). With ``rest_route``, the API is
    reached through ``?rest_route=`` (sites without pretty permalinks).
    """

    def __init__(self, site_url, key, secret, *, query_auth=False, rest_route=False, session=None, sleep=None,
                 timeout=60):
        self.site_url = site_url.rstrip('/')
        self.key = key or ''
        self.secret = secret or ''
        self.query_auth = query_auth
        self.rest_route = rest_route
        self.session = session
        self.sleep = sleep
        self.timeout = timeout

    def url(self, path, namespace=API_PATH):
        route = f"/{namespace}/{path.lstrip('/')}" if namespace else f"/{path.lstrip('/')}"
        if self.rest_route:
            return f'{self.site_url}/?rest_route={route}'
        return f'{self.site_url}/wp-json{route}'

    def request(self, method, path, *, params=None, json=None, namespace=API_PATH, auth=True):
        """ Make a call and give ``(body, headers)``. A 404 gives ``(None, headers)``. """
        params = dict(params or {})
        kwargs = {}
        if auth:
            if self.query_auth:
                params.update(consumer_key=self.key, consumer_secret=self.secret)
            else:
                kwargs['auth'] = (self.key, self.secret)
        if self.sleep:
            kwargs['sleep'] = self.sleep
        url = self.url(path, namespace)
        if params:
            kwargs['params'] = params
        response = request_with_retry(
            method, url, session=self.session, timeout=self.timeout, json=json,
            headers={'Accept': 'application/json', 'User-Agent': 'Odoo Mates WooCommerce Connector'}, **kwargs)
        status = response.status_code
        body = self._body(response)
        message = (body.get('message') if isinstance(body, dict) else None) or (response.text or '')[:300]
        if status in (401, 403):
            raise WooAuthError(f"WooCommerce refused the consumer key of {self.site_url} (HTTP {status}): {message}")
        if status == 404:
            if isinstance(body, dict) and body.get('code') == 'rest_no_route':
                raise WooUserError(f"{self.site_url} has no WooCommerce REST API at {url}: is WooCommerce active, "
                                   f"and are the permalinks set (Settings > Permalinks, not Plain)?")
            return None, response.headers
        if status == 429 or status >= 500:
            raise WooError(f"WooCommerce is not available (HTTP {status}): {message}")
        if status >= 400:
            raise WooUserError(f"WooCommerce refused the call (HTTP {status}): {message}")
        if body is None:
            raise WooUserError(f"{self.site_url} did not answer in JSON: is it a WooCommerce site, and is the REST API "
                               f"reachable at {url}?")
        return body, response.headers

    @staticmethod
    def _body(response):
        try:
            return response.json()
        except ValueError:
            return None

    def get(self, path, params=None, **kwargs):
        return self.request('GET', path, params=params, **kwargs)[0]

    def post(self, path, json=None, **kwargs):
        return self.request('POST', path, json=json, **kwargs)[0]

    def put(self, path, json=None, **kwargs):
        return self.request('PUT', path, json=json, **kwargs)[0]

    def delete(self, path, params=None, **kwargs):
        return self.request('DELETE', path, params=params, **kwargs)[0]

    def paginate(self, path, params=None):
        """ Every item of a list endpoint, page after page (``X-WP-TotalPages``). """
        page = 1
        while True:
            body, headers = self.request('GET', path, params=dict(params or {}, per_page=PAGE_SIZE, page=page))
            if not body:
                return
            yield from body
            try:
                pages = int(headers.get('X-WP-TotalPages') or headers.get('x-wp-totalpages') or 0)
            except ValueError:
                pages = 0
            last_page = page >= pages if pages else len(body) < PAGE_SIZE
            if last_page:
                return
            page += 1

    def upload_media(self, username, app_password, filename, content, mimetype):
        """ Upload a file to the media library of WordPress (``wp/v2/media``), with a WordPress user
        and one of its Application Passwords; gives the media (``id``, ``source_url``). """
        kwargs = {'sleep': self.sleep} if self.sleep else {}
        url = self.url('media', namespace='wp/v2')
        response = request_with_retry(
            'POST', url, session=self.session, timeout=self.timeout, data=content, auth=(username, app_password),
            headers={'Accept': 'application/json', 'User-Agent': 'Odoo Mates WooCommerce Connector',
                     'Content-Type': mimetype, 'Content-Disposition': f'attachment; filename="{filename}"'},
            **kwargs)
        status = response.status_code
        body = self._body(response)
        message = (body.get('message') if isinstance(body, dict) else None) or (response.text or '')[:300]
        if status in (401, 403):
            raise WooAuthError(f"WordPress refused the Application Password of {username} (HTTP {status}): {message}")
        if status == 429 or status >= 500:
            raise WooError(f"WordPress is not available (HTTP {status}): {message}")
        if status >= 400 or not isinstance(body, dict) or not body.get('id'):
            raise WooUserError(f"WordPress refused the image {filename} (HTTP {status}): {message}")
        return body

    def batch(self, path, update=None, create=None, delete=None):
        """ ``POST <path>/batch`` by chunks of 100; gives the items answered. Items refused by
        WooCommerce (``error`` in the answer) raise ``WooUserError`` with their messages. """
        results, errors = [], []
        for key, items in (('update', update), ('create', create), ('delete', delete)):
            items = list(items or [])
            for start in range(0, len(items), BATCH_SIZE):
                body = self.post(f'{path}/batch', {key: items[start:start + BATCH_SIZE]}) or {}
                for item in body.get(key) or []:
                    if isinstance(item, dict) and item.get('error'):
                        errors.append(f"{item.get('id')}: {item['error'].get('message')}")
                    else:
                        results.append(item)
        if errors:
            raise WooUserError("WooCommerce refused some items: " + '; '.join(errors[:10]))
        return results
