from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    credit_limit_block_sale = fields.Boolean(
        string='Block Sales Orders Over the Credit Limit',
        help="Refuse to confirm a sales order that brings the customer over its credit limit. The users allowed to "
             "override the credit limit can still confirm it, and the override is logged on the order.")
