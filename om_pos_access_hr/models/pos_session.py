from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _om_pos_cashier(self, values):
        user, employee = super()._om_pos_cashier(values)
        employee_id = values.get('employee_id') or self.env.context.get('om_pos_employee_id')
        if employee_id:
            employee = self.env['hr.employee'].sudo().browse(int(employee_id)).exists() or None
        return user, employee
