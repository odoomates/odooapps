from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_commission_product_id = fields.Many2one(
        related='company_id.om_commission_product_id', readonly=False)
    om_commission_journal_id = fields.Many2one(
        related='company_id.om_commission_journal_id', readonly=False)
    om_commission_account_id = fields.Many2one(
        related='company_id.om_commission_account_id', readonly=False)
