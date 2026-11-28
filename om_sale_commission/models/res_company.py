from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    om_commission_product_id = fields.Many2one(
        'product.product', string='Commission Product', check_company=True,
        help='Product of the vendor bill lines that pay the commissions.')
    om_commission_journal_id = fields.Many2one(
        'account.journal', string='Commission Journal', check_company=True,
        domain="[('type', '=', 'purchase')]", help='Purchase journal of the commission vendor bills.')
    om_commission_account_id = fields.Many2one(
        'account.account', string='Commission Expense Account', check_company=True,
        help='Expense account of the commission vendor bills. Leave empty to use the account of the product.')
