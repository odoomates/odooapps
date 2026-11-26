from odoo import fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    om_inter_company = fields.Boolean(
        string="Inter-Company", tracking=True,
        help="The account holds balances with the other companies of the group (inter-company receivables, "
             "payables, loans...): the Inter-Company Balances report reads it.")
