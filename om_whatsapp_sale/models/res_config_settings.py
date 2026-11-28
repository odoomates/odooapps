from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_whatsapp_sale_account_id = fields.Many2one(related='company_id.om_whatsapp_sale_account_id', readonly=False)
    om_whatsapp_quotation_template_id = fields.Many2one(
        related='company_id.om_whatsapp_quotation_template_id', readonly=False)
    om_whatsapp_order_template_id = fields.Many2one(related='company_id.om_whatsapp_order_template_id', readonly=False)
    om_whatsapp_order_auto = fields.Boolean(related='company_id.om_whatsapp_order_auto', readonly=False)
