from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def try_cash_in_out(self, _type, amount, reason, partner_id, **kwargs):
        # pos_hr passes the employee on to no one: keep it for the check of the rules of the cashier
        session = self.with_context(om_pos_employee_id=kwargs.get('employee_id'))
        return super(PosSession, session).try_cash_in_out(_type, amount, reason, partner_id, **kwargs)

    def _om_pos_cashier(self, values):
        user, employee = super()._om_pos_cashier(values)
        employee_id = values.get('employee_id') or self.env.context.get('om_pos_employee_id')
        if employee_id:
            employee = self.env['hr.employee'].sudo().browse(int(employee_id)).exists() or None
        return user, employee
