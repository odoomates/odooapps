from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Tell the browser where this user wants the chatter."""
        info = super().session_info()
        user = self.env.user
        if user and not user._is_public():
            info['om_chatter_position'] = user.om_chatter_position or 'auto'
        return info
