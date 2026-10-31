from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    loan_long_term_account_id = fields.Many2one(
        related='company_id.loan_long_term_account_id', readonly=False)
    loan_short_term_account_id = fields.Many2one(
        related='company_id.loan_short_term_account_id', readonly=False)
    loan_interest_account_id = fields.Many2one(
        related='company_id.loan_interest_account_id', readonly=False)
    loan_journal_id = fields.Many2one(related='company_id.loan_journal_id', readonly=False)
    loan_bank_journal_id = fields.Many2one(related='company_id.loan_bank_journal_id', readonly=False)
    lease_long_term_account_id = fields.Many2one(
        related='company_id.lease_long_term_account_id', readonly=False)
    lease_short_term_account_id = fields.Many2one(
        related='company_id.lease_short_term_account_id', readonly=False)
    lease_rou_account_id = fields.Many2one(related='company_id.lease_rou_account_id', readonly=False)
    lease_bill_journal_id = fields.Many2one(related='company_id.lease_bill_journal_id', readonly=False)
