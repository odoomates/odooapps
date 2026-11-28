from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_whatsapp_website_order_template_id = fields.Many2one(
        related='website_id.om_whatsapp_order_template_id', readonly=False)
    om_whatsapp_cart_template_id = fields.Many2one(related='website_id.om_whatsapp_cart_template_id', readonly=False)
