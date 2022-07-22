from odoo import models, fields, api, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    account_credit_limit = fields.Boolean(
        string="Sales Credit Limit", related="company_id.account_credit_limit", readonly=False,
        help="Enable credit limit for the current company.")
    account_default_credit_limit = fields.Monetary(
        string="Default Credit Limit", related="company_id.account_default_credit_limit", readonly=False,
        help="A limit of zero means no limit by default.")
    credit_limit_type = fields.Selection(string="Credit Limit Type", related="company_id.credit_limit_type",
                                         readonly=False)