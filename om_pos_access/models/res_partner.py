from odoo import api, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _om_pos_check_partner_edit(self):
        """ A customer saved from the Point of Sale (its form carries om_pos_partner_edit), by a cashier
        who is not allowed to. """
        if not self.env.context.get('om_pos_partner_edit'):
            return
        Access = self.env['om.pos.access']
        user, employee = self.env['pos.session']._om_pos_cashier({})
        if Access._om_pos_refuse('partner', user, employee):
            raise UserError(Access._om_pos_message('partner'))

    @api.model_create_multi
    def create(self, vals_list):
        self._om_pos_check_partner_edit()
        return super().create(vals_list)

    def write(self, vals):
        self._om_pos_check_partner_edit()
        return super().write(vals)
