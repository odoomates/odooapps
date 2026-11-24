from odoo import fields, models


class OmSubscriptionCloseReason(models.Model):
    _name = 'om.subscription.close.reason'
    _description = 'Subscription Close Reason'
    _order = 'sequence, id'

    name = fields.Char(string='Reason', required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    visible_in_portal = fields.Boolean(
        string='Customer Can Choose', default=True,
        help='Offer this reason to customers who close their subscription from the portal.')
