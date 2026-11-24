from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rental_move_count = fields.Integer(string="Rental Moves", compute='_compute_rental_move_count')

    @api.depends('order_line.rental_move_ids')
    def _compute_rental_move_count(self):
        for order in self:
            order.rental_move_count = len(order.order_line.rental_move_ids)

    def action_view_rental_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Rental Moves"),
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.order_line.rental_move_ids.ids)],
            'context': {'create': False},
        }
