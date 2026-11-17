import base64
import hashlib
import hmac
from unittest.mock import MagicMock

import requests

from odoo.tests import BaseCase, tagged

from odoo.addons.om_connector_base.tools import request_with_retry, verify_hmac_sha256


def _response(status, headers=None):
    response = MagicMock(status_code=status, headers=headers or {})
    return response


@tagged('post_install', '-at_install')
class TestTools(BaseCase):

    def test_hmac_base64_and_hex(self):
        body = b'{"id": 1}'
        digest = hmac.new(b'secret', body, hashlib.sha256).digest()
        self.assertTrue(verify_hmac_sha256('secret', body, base64.b64encode(digest).decode()))
        self.assertTrue(verify_hmac_sha256('secret', body, digest.hex(), encoding='hex'))
        self.assertFalse(verify_hmac_sha256('other', body, base64.b64encode(digest).decode()))
        self.assertFalse(verify_hmac_sha256('secret', b'{"id": 2}', base64.b64encode(digest).decode()))
        self.assertFalse(verify_hmac_sha256('', body, ''))
        self.assertFalse(verify_hmac_sha256('secret', body, None))

    def test_retry_on_rate_limit_then_ok(self):
        session = MagicMock()
        session.request.side_effect = [_response(429, {'Retry-After': '2.5'}), _response(502), _response(200)]
        waits = []
        response = request_with_retry('GET', 'https://x', session=session, sleep=waits.append, backoff=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(waits, [2.5, 2])

    def test_no_retry_on_client_error(self):
        session = MagicMock()
        session.request.return_value = _response(404)
        waits = []
        self.assertEqual(request_with_retry('GET', 'https://x', session=session, sleep=waits.append).status_code, 404)
        self.assertEqual(waits, [])

    def test_network_error_raises_after_retries(self):
        session = MagicMock()
        session.request.side_effect = requests.ConnectionError('down')
        waits = []
        with self.assertRaises(requests.ConnectionError):
            request_with_retry('GET', 'https://x', session=session, sleep=waits.append, retries=2, backoff=1)
        self.assertEqual(waits, [1, 2])
