from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    budget_warning_threshold = fields.Float(
        string='Budget Warning Threshold', default=90.0,
        help="The responsible of a budget is warned when an expense line reaches this percentage of "
             "its planned amount, and again when it goes over it.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    budget_warning_threshold = fields.Float(related='company_id.budget_warning_threshold', readonly=False)
