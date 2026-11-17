from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_connector_base.tools import crypto


@tagged('post_install', '-at_install')
class TestCrypto(TransactionCase):

    def test_round_trip_and_legacy(self):
        token = crypto.encrypt(self.env, 'shpat_secret')
        self.assertTrue(token.startswith(crypto.PREFIX))
        self.assertNotIn('shpat_secret', token)
        self.assertEqual(crypto.decrypt(self.env, token), 'shpat_secret')
        self.assertEqual(crypto.decrypt(self.env, 'plain-old'), 'plain-old', "values stored before stay readable")
        self.assertFalse(crypto.encrypt(self.env, ''))
        self.assertFalse(crypto.decrypt(self.env, False))

    def test_server_key(self):
        with patch.dict(crypto.config.options, {crypto.CONFIG_OPTION: 'server-key-1'}):
            self.assertEqual(crypto.key_source(self.env), 'server')
            token = crypto.encrypt(self.env, 'secret')
            self.assertEqual(crypto.decrypt(self.env, token), 'secret')
        with patch.dict(crypto.config.options, {crypto.CONFIG_OPTION: 'another-key'}), self.assertRaises(UserError):
            crypto.decrypt(self.env, token)
