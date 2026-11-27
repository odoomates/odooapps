from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_whatsapp_invoice_account_id = fields.Many2one(related='company_id.om_whatsapp_invoice_account_id', readonly=False)
    om_whatsapp_invoice_template_id = fields.Many2one(related='company_id.om_whatsapp_invoice_template_id', readonly=False)
    om_whatsapp_refund_template_id = fields.Many2one(related='company_id.om_whatsapp_refund_template_id', readonly=False)
    om_whatsapp_invoice_auto = fields.Boolean(related='company_id.om_whatsapp_invoice_auto', readonly=False)
    om_whatsapp_payment_template_id = fields.Many2one(related='company_id.om_whatsapp_payment_template_id', readonly=False)
    om_whatsapp_payment_auto = fields.Boolean(related='company_id.om_whatsapp_payment_auto', readonly=False)
