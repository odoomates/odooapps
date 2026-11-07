# POS employees on the access profiles: when one of them is the cashier, the Point of Sale rules of the
# profile apply, merged with those set on the employee themselves (the strictest wins).
from odoo import api, fields, models


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    pos_employee_ids = fields.Many2many(
        'hr.employee', 'om_access_profile_pos_employee_rel', 'profile_id', 'employee_id',
        string='POS Employees', tracking=True,
        help="The employees who log in to the Point of Sale with their badge or PIN. When one of them is the "
             "cashier, the Point of Sale restrictions of this profile apply. An employee listed in no profile, "
             "with no rules of their own, follows their Odoo user, or else the Odoo user who opened the shop.")


class OmPosAccess(models.AbstractModel):
    _inherit = 'om.pos.access'

    @api.model
    def _om_pos_employee_rules(self, employee):
        """ Those of the employee themselves and those of the profiles listing them, or None when there
        are neither: they follow their Odoo user. """
        own = super()._om_pos_employee_rules(employee)
        profiles = self.env['om.access.profile'].sudo().search(
            [('pos_employee_ids', 'in', employee.id), ('active', '=', True)])
        if not profiles:
            return own
        listed = self.env['om.access.profile']._om_pos_combine(profiles)
        return listed if own is None else self._om_pos_merge(own, listed)

    @api.model
    def _om_pos_restricted_employees(self):
        listed = self.env['om.access.profile'].sudo().search([('active', '=', True)]).pos_employee_ids
        return super()._om_pos_restricted_employees() | listed
