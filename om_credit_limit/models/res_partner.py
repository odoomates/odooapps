from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    amount_credit_limit = fields.Monetary('Credit Limit')
