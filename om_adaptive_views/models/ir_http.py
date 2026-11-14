from odoo import models

from .om_adapt_rule import param


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """ Tell the web client whether to count how screens are used. """
        info = super().session_info()
        if self.env.user and not self.env.user._is_public():
            info['om_adaptive_learning'] = bool(param(self.env, 'learning'))
        return info
