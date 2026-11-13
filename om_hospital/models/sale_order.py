from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sale_description = fields.Char()
