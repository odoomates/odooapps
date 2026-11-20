from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_reconcile_auto = fields.Boolean(related='company_id.om_reconcile_auto', readonly=False)
    om_reconcile_find_partner = fields.Boolean(related='company_id.om_reconcile_find_partner', readonly=False)
    om_reconcile_tolerance = fields.Monetary(related='company_id.om_reconcile_tolerance', readonly=False)
    om_reconcile_fx_tolerance = fields.Float(related='company_id.om_reconcile_fx_tolerance', readonly=False)
    om_reconcile_tolerance_account_id = fields.Many2one(related='company_id.om_reconcile_tolerance_account_id',
                                                        readonly=False)
    om_bank_fee_account_id = fields.Many2one(related='company_id.om_bank_fee_account_id', readonly=False)

    def set_values(self):
        super().set_values()
        self.env['account.reconcile.model']._om_sync_bank_fee_models(self.company_id)
