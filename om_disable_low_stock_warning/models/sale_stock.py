# -*- coding: utf-8 -*-


from odoo import models, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_uom_qty', 'product_uom', 'route_id')
    def _onchange_product_id_check_availability(self):
        """overriding the original function to remove the low stock warning"""
        return
