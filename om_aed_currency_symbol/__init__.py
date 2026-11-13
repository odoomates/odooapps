# Part of om_aed_currency_symbol (Odoo Mates). License: LGPL-3.
from . import models
from .models.res_currency import DIRHAM_SIGN


def post_init_hook(env):
    """Show the UAE Dirham sign for AED (all companies share the currency record)."""
    env['res.currency']._om_set_dirham_sign()


def uninstall_hook(env):
    """Give AED its standard symbol back (unless Odoo's own data already uses the Dirham sign)."""
    env['res.currency']._om_restore_aed_symbol()
