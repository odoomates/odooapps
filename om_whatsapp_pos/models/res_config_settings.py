from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_om_whatsapp_receipt = fields.Boolean(related='pos_config_id.om_whatsapp_receipt', readonly=False)
    pos_om_whatsapp_receipt_template_id = fields.Many2one(
        related='pos_config_id.om_whatsapp_receipt_template_id', readonly=False)
    pos_om_whatsapp_account_id = fields.Many2one(related='pos_config_id.om_whatsapp_account_id', readonly=False)
