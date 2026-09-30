from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    currency_reval_date = fields.Date(
        string='Revaluation Date', readonly=True, copy=False, index='btree_not_null',
        help="The date the open foreign currency balances were revalued at, for the adjustment entries of the "
             "currency revaluation.")
