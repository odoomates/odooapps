from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # the last choices of the tax closing wizard, proposed again on the next closing
    om_tax_closing_journal_id = fields.Many2one(
        'account.journal', string='Tax Closing Journal', check_company=True, domain=[('type', '=', 'general')])
    om_tax_payable_account_id = fields.Many2one(
        'account.account', string='Tax Payable Account', check_company=True,
        help="Receives the tax owed for a closed period.")
    om_tax_receivable_account_id = fields.Many2one(
        'account.account', string='Tax Receivable Account', check_company=True,
        help="Receives the tax to be refunded for a closed period.")
