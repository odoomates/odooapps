from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    om_barcode_qty = fields.Float(
        string="Scanned Quantity", digits='Product Unit', copy=False,
        help="Quantity scanned in the Barcode app, set as the quantity of the line on validation.")
    om_barcode_dest_scanned = fields.Boolean(
        string="Destination Scanned", copy=False,
        help="The destination location of the line was scanned in the Barcode app.")
    om_barcode_packed = fields.Boolean(
        string="Packed by Scan", copy=False,
        help="The line was put in its destination package in the Barcode app.")
