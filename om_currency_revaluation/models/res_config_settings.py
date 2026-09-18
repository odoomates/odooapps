from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    currency_reval_journal_id = fields.Many2one(
        related='company_id.currency_reval_journal_id', readonly=False)
    currency_reval_gain_account_id = fields.Many2one(
        related='company_id.currency_reval_gain_account_id', readonly=False)
    currency_reval_loss_account_id = fields.Many2one(
        related='company_id.currency_reval_loss_account_id', readonly=False)
    currency_reval_reverse = fields.Boolean(
        related='company_id.currency_reval_reverse', readonly=False)
