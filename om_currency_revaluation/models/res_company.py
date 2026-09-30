from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    currency_reval_journal_id = fields.Many2one(
        'account.journal', string='Currency Revaluation Journal', check_company=True,
        domain="[('type', '=', 'general')]",
        help="The journal of the adjustment entries of the currency revaluations.")
    currency_reval_gain_account_id = fields.Many2one(
        'account.account', string='Unrealized Gain Account', check_company=True,
        domain="[('deprecated', '=', False)]",
        help="The account credited when the open foreign currency balances are worth more at the closing rate.")
    currency_reval_loss_account_id = fields.Many2one(
        'account.account', string='Unrealized Loss Account', check_company=True,
        domain="[('deprecated', '=', False)]",
        help="The account debited when the open foreign currency balances are worth less at the closing rate.")
    currency_reval_reverse = fields.Boolean(
        string='Reverse the Revaluation', default=True,
        help="Reverse the adjustment entry at the start of the next period: the gains and the losses are only "
             "made when the invoices are paid.")
