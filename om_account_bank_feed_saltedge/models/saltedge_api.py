""" A small client of the Salt Edge Account Information API, version 6: https://docs.saltedge.com/v6/ """
import base64
import json
import logging
import re
import time
from urllib.parse import urlencode

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from odoo.addons.om_account_bank_feed.models.bank_feed_connection import BankFeedError

_logger = logging.getLogger(__name__)

API_URL = 'https://www.saltedge.com/api/v6'
TIMEOUT = 30
MAX_ATTEMPTS = 3
MAX_WAIT = 10
PER_PAGE = 1000
MAX_PAGES = 200

# the errors after which the consent of the bank must be given again
EXPIRED_ERRORS = {
    'AispConsentExpired', 'AispConsentRevoked', 'AispConsentNotFound', 'ConsentExpired', 'ConsentRevoked',
}


def normalize_pem(key):
    """ :return: the PEM key with its line breaks, which are lost when it is pasted in a one line field """
    key = (key or '').strip()
    if '\n' in key:
        return key
    match = re.match(r'^(-----BEGIN [A-Z ]+-----)\s*(.+?)\s*(-----END [A-Z ]+-----)$', key)
    if not match:
        return key
    body = re.sub(r'\s+', '', match.group(2))
    lines = [body[index:index + 64] for index in range(0, len(body), 64)]
    return '\n'.join([match.group(1), *lines, match.group(3)])


class SaltEdgeAPI:

    def __init__(self, env, app_id, secret, private_key=None, url=None):
        self.env = env
        self.app_id = app_id
        self.secret = secret
        self.private_key = private_key
        self.url = (url or API_URL).rstrip('/')

    def _signature_headers(self, method, url, body):
        """ The signature Salt Edge requires from the live applications: the base64 RSA SHA256 signature of
        ``expires_at|method|url|body`` with the private key of the application. """
        expires_at = str(int(time.time()) + 60)
        try:
            key = serialization.load_pem_private_key(normalize_pem(self.private_key).encode(), password=None)
        except (ValueError, TypeError) as error:
            raise BankFeedError(self.env._('The Salt Edge private key is not a valid PEM key: %s', error)) from error
        signature = key.sign(f'{expires_at}|{method}|{url}|{body}'.encode(), padding.PKCS1v15(), hashes.SHA256())
        return {'Expires-at': expires_at, 'Signature': base64.b64encode(signature).decode()}

    def request(self, method, path, params=None, data=None):
        """ :return: the JSON answer of Salt Edge
        :raise BankFeedError: when Salt Edge refuses the request or cannot be reached
        """
        if not self.app_id or not self.secret:
            raise BankFeedError(self.env._(
                'Enter the App ID and the Secret of your Salt Edge account in the settings of the accounting.'))
        url = self.url + path
        if params:
            url += '?' + urlencode(params)
        body = json.dumps({'data': data}) if data is not None else ''
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'App-id': self.app_id,
            'Secret': self.secret,
        }
        if self.private_key:
            headers.update(self._signature_headers(method, url, body))
        response = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = requests.request(method, url, data=body.encode() if body else None, headers=headers,
                                            timeout=TIMEOUT)
            except requests.RequestException as error:
                _logger.warning("Salt Edge request %s %s failed: %s", method, path, error)
                raise BankFeedError(self.env._('Salt Edge could not be reached: %s', error)) from error
            if response.status_code != 429 or attempt == MAX_ATTEMPTS - 1:
                break
            # too many requests: wait as long as Salt Edge asks, a few seconds at most
            try:
                wait = int(response.headers.get('Retry-After') or 0)
            except ValueError:
                wait = 0
            time.sleep(min(max(wait, 2 ** attempt), MAX_WAIT))
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            raise self._error(response, payload)
        return payload

    def _error(self, response, payload):
        error = payload.get('error') if isinstance(payload.get('error'), dict) else payload
        error_class = error.get('class') or error.get('error_class') or str(response.status_code)
        message = error.get('message') or error.get('error_message') or response.reason or ''
        _logger.info("Salt Edge error %s: %s (request %s)", error_class, message, payload.get('request_id'))
        if response.status_code == 429:
            text = self.env._('Salt Edge received too many requests: the sync is tried again later.')
        elif error_class == 'RateLimitExceeded':
            text = self.env._('Salt Edge refuses more parallel sessions for now: try again in a few minutes.')
        elif error_class in EXPIRED_ERRORS:
            text = self.env._('The consent of the bank has expired or was revoked: renew it.')
        else:
            text = self.env._('Salt Edge refused the request: %(message)s (%(code)s)',
                              message=message, code=error_class)
        exception = BankFeedError(text, expired=error_class in EXPIRED_ERRORS)
        exception.error_class = error_class
        return exception

    def paginate(self, path, params):
        """ :return: all the records of a list, reading the pages with ``from_id`` """
        params = {**params, 'per_page': PER_PAGE}
        records = []
        for _page in range(MAX_PAGES):
            payload = self.request('GET', path, params=params)
            records += payload.get('data') or []
            next_id = (payload.get('meta') or {}).get('next_id')
            if not next_id:
                break
            params['from_id'] = next_id
        return records
