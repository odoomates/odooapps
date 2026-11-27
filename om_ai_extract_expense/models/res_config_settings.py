from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    om_ai_expense_read_on_upload = fields.Boolean(
        string='Read Uploaded Receipts with AI', config_parameter='om_ai_extract_expense.read_on_upload')
