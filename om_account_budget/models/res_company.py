from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    budget_warning_threshold = fields.Float(
        string='Budget Warning Threshold', default=90.0,
        help="The responsible of a budget is warned when an expense line reaches this percentage of "
             "its planned amount, and again when it goes over it.",
    )
    budget_block_documents = fields.Boolean(
        string='Block Documents Over Budget',
        help="Only the accounting managers can post the vendor bills (and confirm the purchase orders) going over "
             "the planned amount of a budget line; the other users see a warning.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    budget_warning_threshold = fields.Float(related='company_id.budget_warning_threshold', readonly=False)
    budget_block_documents = fields.Boolean(related='company_id.budget_block_documents', readonly=False)
