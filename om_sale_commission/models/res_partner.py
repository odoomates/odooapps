from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    om_commission_grade_id = fields.Many2one(
        'om.commission.grade', string='Reseller Grade', index='btree_not_null',
        help='Reseller plans of this grade apply to the sales this partner brings.')
    om_referrer_id = fields.Many2one(
        'res.partner', string='Referred By', index='btree_not_null',
        help='Reseller who brought this customer: set by default as referrer on the sales orders of the customer.')
