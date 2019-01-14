# -*- coding: utf-8 -*-

from odoo import models, api


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def create(self, vals):
        order = super(PosOrder, self).create(vals)
        lines = order.lines.mapped('id')
        self.pos_order_updates(order.id, lines)
        return order

    @api.model
    def pos_order_updates(self, order_id, lines):
        channel_name = "pos_order_sync"
        data = {'order_id': order_id, 'lines': lines}
        self.env['pos.config'].send_to_all_poses(channel_name, data)
