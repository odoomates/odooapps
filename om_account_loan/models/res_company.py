from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    loan_long_term_account_id = fields.Many2one(
        'account.account', string='Long-term Loan Account', check_company=True)
    loan_short_term_account_id = fields.Many2one(
        'account.account', string='Short-term Loan Account', check_company=True)
    loan_interest_account_id = fields.Many2one(
        'account.account', string='Loan Interest Account', check_company=True)
    loan_journal_id = fields.Many2one(
        'account.journal', string='Loan Journal', check_company=True, domain="[('type', '=', 'general')]")
    loan_bank_journal_id = fields.Many2one(
        'account.journal', string='Loan Bank Journal', check_company=True,
        domain="[('type', 'in', ('bank', 'cash'))]")
    lease_long_term_account_id = fields.Many2one(
        'account.account', string='Long-term Lease Liability Account', check_company=True)
    lease_short_term_account_id = fields.Many2one(
        'account.account', string='Short-term Lease Liability Account', check_company=True)
    lease_rou_account_id = fields.Many2one(
        'account.account', string='Right-of-use Asset Account', check_company=True)
    lease_bill_journal_id = fields.Many2one(
        'account.journal', string='Lease Bill Journal', check_company=True, domain="[('type', '=', 'purchase')]")
