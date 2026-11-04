from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    credit_limit_block = fields.Boolean(related='company_id.credit_limit_block', readonly=False)
