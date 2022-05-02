from odoo import models, fields, api, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_credit_limit = fields.Boolean()
    account_default_credit_limit = fields.Monetary()
    credit_limit_type = fields.Selection([('warning', 'Warning'), ('block', 'Block')])