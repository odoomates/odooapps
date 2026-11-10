from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pdc_receivable_account_id = fields.Many2one(related='company_id.pdc_receivable_account_id', readonly=False)
    pdc_payable_account_id = fields.Many2one(related='company_id.pdc_payable_account_id', readonly=False)
    pdc_journal_id = fields.Many2one(related='company_id.pdc_journal_id', readonly=False)
