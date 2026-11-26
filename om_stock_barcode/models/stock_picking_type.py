from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    om_barcode_require_source = fields.Boolean(
        string="Scan Source Location",
        help="In the Barcode app, the source location must be scanned before its products.")
    om_barcode_require_dest = fields.Boolean(
        string="Scan Destination Location",
        help="In the Barcode app, the destination location of the scanned products must be scanned "
             "before the transfer can be validated.")
    om_barcode_require_package = fields.Boolean(
        string="Scan Package",
        help="In the Barcode app, the scanned products must be put in a package before the transfer "
             "can be validated.")
    om_barcode_allow_unplanned = fields.Boolean(
        string="Allow Unplanned Products", default=True,
        help="In the Barcode app, products that are not in the transfer can be added by scanning them.")
