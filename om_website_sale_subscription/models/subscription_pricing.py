from odoo import fields, models


class OmSubscriptionPricing(models.Model):
    _inherit = 'om.subscription.pricing'

    plan_website_published = fields.Boolean(related='plan_id.website_published', string='On Website')
