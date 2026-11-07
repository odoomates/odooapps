from odoo import models
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _om_pos_cashier(self, values):
        """ (user, employee) moving cash: om_pos_access_hr knows the employee. """
        return self.env.user, None

    def try_cash_in_out(self, _type, amount, reason, partner_id, **kwargs):
        Access = self.env['om.pos.access']
        user, employee = self._om_pos_cashier(kwargs)
        if Access._om_pos_refuse('cash_move', user, employee):
            raise UserError(Access._om_pos_message('cash_move'))
        return super().try_cash_in_out(_type, amount, reason, partner_id, **kwargs)

    def close_session_from_ui(self, *args, **kwargs):
        Access = self.env['om.pos.access']
        user, employee = self._om_pos_cashier({})
        if Access._om_pos_refuse('close', user, employee):
            raise UserError(Access._om_pos_message('close'))
        return super().close_session_from_ui(*args, **kwargs)
