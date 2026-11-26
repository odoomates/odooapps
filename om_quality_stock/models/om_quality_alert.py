from odoo import fields, models


class OmQualityAlert(models.Model):
    _inherit = 'om.quality.alert'

    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number', index='btree_not_null', check_company=True,
                             domain="[('product_id', '=', product_id)]")
    picking_id = fields.Many2one('stock.picking', string='Transfer', index='btree_not_null', check_company=True)
