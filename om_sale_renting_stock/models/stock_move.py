from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    rental_line_id = fields.Many2one(
        'sale.order.line', string="Rental Order Line", index='btree_not_null', ondelete='set null')
