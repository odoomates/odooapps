from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    credit_limit_block_sale = fields.Boolean(related='company_id.credit_limit_block_sale', readonly=False)
