from odoo import models


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    def _planning_get_partner(self):
        """ The employee receives the schedule on the contact of their user, or else on their work
        contact (work email). """
        partner = super()._planning_get_partner()
        employee = self.employee_id[:1]
        if not employee:
            return partner
        return employee.user_id.partner_id or employee.work_contact_id or partner

    def _planning_get_manager_users(self):
        """ Users who approve the planning requests of the resource: the manager of the employee
        and the manager of their department. """
        employee = self.sudo().employee_id[:1]
        return (employee.parent_id.user_id | employee.department_id.manager_id.user_id).filtered('active')
