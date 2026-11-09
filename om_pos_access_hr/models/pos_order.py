from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _om_pos_cashier(self, order):
        user, employee = super()._om_pos_cashier(order)
        employee_id = order.get('employee_id')
        if isinstance(employee_id, (list, tuple)):
            employee_id = employee_id[0] if employee_id else False
        if employee_id:
            employee = self.env['hr.employee'].sudo().browse(int(employee_id)).exists() or None
        return user, employee

    @api.model
    def _om_pos_cancel_cashier(self):
        user, employee = super()._om_pos_cancel_cashier()
        employee_id = self.env.context.get('om_pos_employee_id')
        if employee_id:
            employee = self.env['hr.employee'].sudo().browse(int(employee_id)).exists() or None
        return user, employee
