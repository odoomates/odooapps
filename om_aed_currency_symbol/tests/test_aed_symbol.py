# Part of om_aed_currency_symbol (Odoo Mates). License: LGPL-3.
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.res_currency import DIRHAM_SIGN


@tagged('post_install', '-at_install')
class TestAedSymbol(TransactionCase):

    def setUp(self):
        super().setUp()
        self.aed = self.env.ref('base.AED')

    def test_installed_symbol(self):
        self.assertEqual(self.aed.symbol, DIRHAM_SIGN)
        self.assertEqual(self.aed.position, 'before')
        self.assertTrue(self.aed.format(1234.5).startswith(DIRHAM_SIGN))

    def _patch_native_symbol(self, symbol):
        return patch.object(type(self.env['res.currency']), '_om_native_aed_symbol', return_value=symbol)

    def test_restore_and_set_again(self):
        with self._patch_native_symbol('AED'):
            self.env['res.currency']._om_restore_aed_symbol()
        self.assertEqual((self.aed.symbol, self.aed.position), ('AED', 'after'))
        self.env['res.currency']._om_set_dirham_sign()
        self.assertEqual((self.aed.symbol, self.aed.position), (DIRHAM_SIGN, 'before'))

    def test_replaces_workaround_symbols_keeps_custom(self):
        for old in ('ᴁ', 'د.إ', 'Dhs'):
            self.aed.symbol = old
            self.env['res.currency']._om_set_dirham_sign()
            self.assertEqual(self.aed.symbol, DIRHAM_SIGN, old)
        self.aed.symbol = 'MyDH'
        self.env['res.currency']._om_set_dirham_sign()
        self.assertEqual(self.aed.symbol, 'MyDH')
        self.aed.action_om_use_dirham_sign()
        self.assertEqual(self.aed.symbol, DIRHAM_SIGN)

    def test_restore_leaves_custom_symbol(self):
        self.aed.symbol = 'MyDH'
        with self._patch_native_symbol('AED'):
            self.env['res.currency']._om_restore_aed_symbol()
        self.assertEqual(self.aed.symbol, 'MyDH')

    def test_restore_leaves_symbol_when_odoo_supports_the_sign(self):
        """Once Odoo's own data uses U+20C3, uninstalling this module must not change the symbol."""
        self.assertEqual((self.aed.symbol, self.aed.position), (DIRHAM_SIGN, 'before'))
        with self._patch_native_symbol(DIRHAM_SIGN):
            self.env['res.currency']._om_restore_aed_symbol()
        self.assertEqual((self.aed.symbol, self.aed.position), (DIRHAM_SIGN, 'before'))

    def test_native_symbol_lookup(self):
        native = self.env['res.currency']._om_native_aed_symbol()
        self.assertTrue(native is None or isinstance(native, str))


@tagged('post_install', '-at_install')
class TestAedSymbolBrowser(HttpCase):

    def test_font_loaded_without_changing_fonts(self):
        """The sign's font is available, but the interface and code fonts are untouched."""
        code = """
            (async () => {
                await document.fonts.ready;
                const loaded = await document.fonts.load("16px 'OM UAE Dirham'", "\\u20c3");
                const faces = [...document.fonts].filter(f => f.family.replace(/["']/g, '') === 'OM UAE Dirham');
                const body = getComputedStyle(document.body).fontFamily;
                const pre = document.createElement('pre');
                document.body.appendChild(pre);
                const mono = getComputedStyle(pre).fontFamily;
                if (!faces.length || !loaded.length) {
                    console.error('UAE Dirham font face missing');
                } else if (body.includes('OM UAE Dirham')) {
                    console.error('body font-family was changed: ' + body);
                } else if (!/mono|consolas|menlo|courier/i.test(mono)) {
                    console.error('monospace font was changed: ' + mono);
                } else {
                    console.log('test successful');
                }
            })();
        """
        self.browser_js('/odoo', code, ready="!!document.querySelector('.o_main_navbar')", login='admin')
