from odoo import api, models


class OmPosAccess(models.AbstractModel):
    _inherit = 'om.pos.access'

    @api.model
    def _om_pos_employee_rules(self, employee):
        """ The rules of an employee who has some of their own, or None: they follow their Odoo user.
        om_access_manager_pos_hr adds those of the access profiles listing them. """
        employee = employee.sudo()
        return employee._om_pos_own_rules() if employee.om_pos_own_rules else None

    @api.model
    def _om_pos_restricted_employees(self):
        """ The employees whose rules the shop loads: those not following their user. """
        return self.env['hr.employee'].sudo().search([('om_pos_own_rules', '=', True)])

    @api.model
    def _om_pos_rules(self, user, employee=None):
        if employee:
            rules = self._om_pos_employee_rules(employee)
            if rules is not None:
                return rules
            if employee.user_id:
                return self._om_pos_user_rules(employee.user_id)
        return super()._om_pos_rules(user, employee)

    @api.model
    def _om_pos_restrictions(self, config):
        result = super()._om_pos_restrictions(config)
        result['employees'] = {}
        for employee in self._om_pos_restricted_employees():
            rules = self._om_pos_employee_rules(employee)
            # rules restricting nothing still count: they replace those of the user
            if rules is not None:
                result['employees'][str(employee.id)] = rules
        return result
