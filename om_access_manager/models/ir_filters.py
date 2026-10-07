# Saved searches, refused to a profile with 'No Saved Searches'.
from odoo import _, api, models


class IrFilters(models.Model):
    _inherit = 'ir.filters'

    def _om_check_favorites(self):
        rules = self.env['om.access.profile']._current_rules()
        if rules.enabled and rules.has_flag('block_favorites'):
            raise self.env['om.access.profile']._om_refusal(
                _("Your access profile does not allow saving searches."), model=self._name)

    @api.model
    def create_or_replace(self, vals):
        # saving a search from the web client, on Odoo 15
        self._om_check_favorites()
        return super().create_or_replace(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if self._om_rpc_entry('create'):
            self._om_check_favorites()
        return super().create(vals_list)

    def write(self, vals):
        if self._om_rpc_entry('write'):
            self._om_check_favorites()
        return super().write(vals)
