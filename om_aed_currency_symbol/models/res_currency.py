# Part of om_aed_currency_symbol (Odoo Mates). License: LGPL-3.
import logging

from lxml import etree

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

# U+20C3 UAE DIRHAM SIGN (Unicode 18.0), unveiled by the Central Bank of the UAE in March 2025.
DIRHAM_SIGN = '⃃'
STANDARD_SYMBOL = 'AED'
# Symbols other modules or users used for AED; they are replaced by the real sign.
REPLACEABLE_SYMBOLS = {STANDARD_SYMBOL, 'Dhs', 'DH', 'Dh', 'د.إ', 'دإ', 'ᴁ', 'Æ', ''}


class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _om_aed_currency(self):
        currency = self.env.ref('base.AED', raise_if_not_found=False)
        if not currency:
            currency = self.with_context(active_test=False).search([('name', '=', 'AED')], limit=1)
        return currency.sudo()

    @api.model
    def _om_set_dirham_sign(self, force=False):
        """Set U+20C3 as the AED symbol, placed before the amount.

        A symbol that a user typed on purpose (not in the known list) is kept unless ``force``.
        """
        currency = self._om_aed_currency()
        if not currency:
            _logger.info('om_aed_currency_symbol: no AED currency found, nothing to do.')
            return False
        if currency.symbol == DIRHAM_SIGN and currency.position == 'before':
            return True
        if force or currency.symbol in REPLACEABLE_SYMBOLS or currency.symbol == DIRHAM_SIGN:
            currency.write({'symbol': DIRHAM_SIGN, 'position': 'before'})
            return True
        _logger.info('om_aed_currency_symbol: AED symbol %r kept (custom value).', currency.symbol)
        return False

    @api.model
    def _om_native_aed_symbol(self):
        """Symbol that Odoo's own currency data gives to AED, or None if it cannot be read.

        This module is a bridge until Odoo supports U+20C3 natively. Once Odoo's data uses the sign
        itself, uninstalling the module must not overwrite it.
        """
        try:
            with file_open('base/data/res_currency_data.xml', 'rb') as data_file:
                nodes = etree.parse(data_file).xpath("//record[@id='AED']/field[@name='symbol']")
        except (OSError, etree.XMLSyntaxError, ValueError):
            _logger.info('om_aed_currency_symbol: could not read the native AED symbol of Odoo.')
            return None
        return nodes[0].text if nodes else None

    @api.model
    def _om_restore_aed_symbol(self):
        """Give AED its standard symbol back, unless Odoo itself already uses the Dirham sign."""
        currency = self._om_aed_currency()
        if not currency or currency.symbol != DIRHAM_SIGN:
            return True
        if self._om_native_aed_symbol() == DIRHAM_SIGN:
            # Odoo's own data already uses U+20C3: leave the symbol exactly as Odoo defines it.
            return True
        currency.write({'symbol': STANDARD_SYMBOL, 'position': 'after'})
        return True

    def action_om_use_dirham_sign(self):
        """Button on the currency form: use the Dirham sign even if a custom symbol was set."""
        self._om_set_dirham_sign(force=True)
        return True
