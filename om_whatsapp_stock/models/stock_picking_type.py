from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    om_whatsapp_done_template_id = fields.Many2one(
        'om.whatsapp.template', string='WhatsApp When Done', domain="[('model', '=', 'stock.picking')]",
        help="Sent once to the contact of each transfer of this type when it is done, e.g. Delivery: Shipped with "
             "the tracking link of the carrier. Empty: no message.")
