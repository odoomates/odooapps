from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        res = super().session_info()
        if self.env.user._is_internal():
            res['om_ai_writer'] = self.env.user.has_group('om_ai.group_ai_user')
        return res
