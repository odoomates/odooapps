""" A small client of the Shopify Admin GraphQL API. """
import logging
import re
import time
from urllib.parse import urlencode

from odoo.exceptions import UserError

from odoo.addons.om_connector_base.tools import RetryableJobError, request_with_retry, verify_hmac_sha256

_logger = logging.getLogger(__name__)

DEFAULT_API_VERSION = '2026-10'
DEFAULT_SCOPES = ','.join([
    'read_products', 'write_products', 'read_inventory', 'write_inventory', 'read_locations', 'read_orders',
    'write_orders', 'read_customers', 'read_fulfillments', 'write_fulfillments',
    'read_merchant_managed_fulfillment_orders', 'write_merchant_managed_fulfillment_orders', 'read_publications',
    'write_publications',
])
SHOP_DOMAIN_RE = re.compile(r'^[a-z0-9][a-z0-9-]*\.myshopify\.com$')


class ShopifyError(Exception):
    """ An error of the Shopify API that may pass if the call is made again later. """


class ShopifyThrottledError(RetryableJobError, ShopifyError):
    """ Shopify still limits the calls after waiting: the job is tried again later. """


class ShopifyUserError(UserError):
    """ Shopify refused the data (``userErrors`` of a mutation, or a wrong query): making the same
    call again gives the same error. """


class ShopifyAuthError(UserError):
    """ The access token is wrong, expired, or lacks a scope. """


def normalize_shop_domain(value):
    """ ``https://My-Shop.myshopify.com/admin`` or ``my-shop`` → ``my-shop.myshopify.com``. """
    value = (value or '').strip().lower()
    value = re.sub(r'^https?://', '', value).split('/')[0]
    if value and '.' not in value:
        value += '.myshopify.com'
    return value


def is_valid_shop_domain(value):
    return bool(SHOP_DOMAIN_RE.match(value or ''))


def topic_to_enum(topic):
    """ ``orders/create`` (header of a webhook) → ``ORDERS_CREATE`` (GraphQL enum). """
    return (topic or '').strip().upper().replace('/', '_')


class ShopifyClient:
    """ Calls the Admin GraphQL API of one store with an access token.

    Throttling is handled here: a call refused because the store has no points left waits until
    enough points are back, as given by the cost of the call, and is made again.
    """

    def __init__(self, shop_domain, access_token, api_version=DEFAULT_API_VERSION, *, session=None,
                 sleep=time.sleep, timeout=60, max_throttle_wait=60):
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.api_version = api_version or DEFAULT_API_VERSION
        self.session = session
        self.sleep = sleep
        self.timeout = timeout
        self.max_throttle_wait = max_throttle_wait
        self.last_cost = None

    @property
    def url(self):
        return f'https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json'

    def execute(self, query, variables=None):
        """ Run a query or a mutation and give its ``data``. """
        waited = 0
        while True:
            response = request_with_retry(
                'POST', self.url, session=self.session, sleep=self.sleep, timeout=self.timeout,
                json={'query': query, 'variables': variables or {}},
                headers={'X-Shopify-Access-Token': self.access_token or '', 'Content-Type': 'application/json',
                         'Accept': 'application/json'},
            )
            status = response.status_code
            if status in (401, 403):
                raise ShopifyAuthError(f"Shopify refused the access token of {self.shop_domain} (HTTP {status}).")
            if status == 402:
                raise ShopifyUserError(f"The store {self.shop_domain} is frozen: its Shopify plan is unpaid.")
            if status == 404:
                raise ShopifyUserError(f"No store {self.shop_domain}, or API version {self.api_version} is not "
                                       f"supported anymore.")
            if status == 423:
                raise ShopifyUserError(f"The store {self.shop_domain} is locked by Shopify.")
            if status == 429 or status >= 500:
                raise ShopifyError(f"Shopify is not available (HTTP {status}).")
            if status >= 400:
                raise ShopifyUserError(f"Shopify refused the call (HTTP {status}): {response.text[:500]}")
            data = response.json()
            extensions = data.get('extensions') or {}
            self.last_cost = extensions.get('cost')
            errors = data.get('errors')
            if not errors:
                return data.get('data') or {}
            codes = {(e.get('extensions') or {}).get('code') for e in errors if isinstance(e, dict)}
            if 'THROTTLED' in codes:
                wait = self._throttle_wait(extensions.get('cost'))
                if waited + wait > self.max_throttle_wait:
                    raise ShopifyThrottledError(f"Shopify limits the calls of {self.shop_domain}.",
                                                delay=max(int(wait), 30))
                _logger.info("Shopify %s: throttled, new try in %.1fs", self.shop_domain, wait)
                self.sleep(wait)
                waited += wait
                continue
            message = '; '.join(e.get('message', str(e)) if isinstance(e, dict) else str(e)
                                for e in (errors if isinstance(errors, list) else [errors]))
            if 'ACCESS_DENIED' in codes:
                raise ShopifyAuthError(f"Shopify denied the access: {message}")
            if 'INTERNAL_SERVER_ERROR' in codes:
                raise ShopifyError(f"Shopify error: {message}")
            raise ShopifyUserError(f"Shopify error: {message}")

    @staticmethod
    def _throttle_wait(cost):
        cost = cost or {}
        status = cost.get('throttleStatus') or {}
        requested = cost.get('requestedQueryCost') or cost.get('actualQueryCost') or 50
        available = status.get('currentlyAvailable') or 0
        restore = status.get('restoreRate') or 50
        return max((requested - available) / restore, 1.0)

    def mutate(self, query, variables, field, errors_key='userErrors'):
        """ Run a mutation and give its result ``field``; its ``userErrors`` raise ``ShopifyUserError``. """
        result = (self.execute(query, variables) or {}).get(field) or {}
        user_errors = result.get(errors_key) or []
        if user_errors:
            raise ShopifyUserError('; '.join(
                f"{'.'.join(map(str, e.get('field') or []))}: {e.get('message')}" if e.get('field') else e.get('message', '')
                for e in user_errors))
        return result

    def paginate(self, query, variables, path):
        """ Give every node of a connection, page after page.

        The query takes a ``$cursor: String`` variable and selects ``nodes`` and
        ``pageInfo { hasNextPage endCursor }`` of the connection at ``path`` (``products``,
        ``order.lineItems``…).
        """
        variables = dict(variables or {}, cursor=None)
        while True:
            data = self.execute(query, dict(variables))
            connection = data
            for key in path.split('.'):
                connection = (connection or {}).get(key)
            if not connection:
                return
            yield from connection.get('nodes') or []
            page_info = connection.get('pageInfo') or {}
            if not page_info.get('hasNextPage'):
                return
            variables['cursor'] = page_info.get('endCursor')

    @staticmethod
    def _token_request(shop_domain, data, *, session=None, sleep=time.sleep, what='credentials'):
        response = request_with_retry(
            'POST', f'https://{shop_domain}/admin/oauth/access_token', session=session, sleep=sleep, timeout=30,
            data=data, headers={'Accept': 'application/json'},
        )
        if response.status_code >= 400:
            try:
                detail = response.json()
                detail = detail.get('error_description') or detail.get('errors') or detail.get('error') or detail
            except ValueError:
                detail = response.text[:300]
            raise ShopifyAuthError(f"Shopify refused the {what} of {shop_domain}: {detail}")
        return response.json()

    @staticmethod
    def fetch_client_credentials_token(shop_domain, client_id, client_secret, *, session=None, sleep=time.sleep):
        """ The access token of an app of the Dev Dashboard installed on a store of its organization
        (client credentials grant). Gives ``(token, seconds_valid)``. """
        data = ShopifyClient._token_request(shop_domain, {
            'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret,
        }, session=session, sleep=sleep, what='client ID and secret')
        return data['access_token'], int(data.get('expires_in') or 86399)

    @staticmethod
    def authorize_url(shop_domain, client_id, scopes, redirect_uri, state):
        """ The page of Shopify where the merchant installs the app (authorization code grant). """
        return f'https://{shop_domain}/admin/oauth/authorize?' + urlencode({
            'client_id': client_id, 'scope': scopes, 'redirect_uri': redirect_uri, 'state': state,
        })

    @staticmethod
    def verify_oauth_query(client_secret, params):
        """ Whether the query of a redirection of Shopify (install or callback) is signed by the app:
        the HMAC-SHA256, in hex, of the other parameters sorted by name. """
        signature = params.get('hmac')
        message = '&'.join(f'{key}={value}' for key, value in sorted(params.items())
                           if key not in ('hmac', 'signature'))
        return verify_hmac_sha256(client_secret, message.encode(), signature, encoding='hex')

    @staticmethod
    def fetch_oauth_token(shop_domain, client_id, client_secret, code, *, expiring=True, session=None,
                          sleep=time.sleep):
        """ Exchange the code of the callback for an offline access token: with ``expiring``, a token of
        one hour and a refresh token. Gives the answer of Shopify (access_token, scope, expires_in,
        refresh_token, refresh_token_expires_in). """
        data = {'client_id': client_id, 'client_secret': client_secret, 'code': code}
        if expiring:
            data['expiring'] = '1'
        return ShopifyClient._token_request(shop_domain, data, session=session, sleep=sleep, what='authorization')

    @staticmethod
    def refresh_oauth_token(shop_domain, client_id, client_secret, refresh_token, *, session=None, sleep=time.sleep):
        """ A new access token, and a new refresh token: the old one stops working at once. """
        return ShopifyClient._token_request(shop_domain, {
            'grant_type': 'refresh_token', 'client_id': client_id, 'client_secret': client_secret,
            'refresh_token': refresh_token,
        }, session=session, sleep=sleep, what='refresh token')
