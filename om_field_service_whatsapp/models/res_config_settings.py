from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fs_whatsapp_account_id = fields.Many2one(related='company_id.fs_whatsapp_account_id', readonly=False)
    fs_whatsapp_planned_id = fields.Many2one(related='company_id.fs_whatsapp_planned_id', readonly=False)
    fs_whatsapp_on_the_way_id = fields.Many2one(related='company_id.fs_whatsapp_on_the_way_id', readonly=False)
    fs_whatsapp_report_id = fields.Many2one(related='company_id.fs_whatsapp_report_id', readonly=False)
