from odoo import fields, models


class OmShopifyWebhook(models.Model):
    """ A webhook subscription of a store, made by Odoo. """
    _name = 'om.shopify.webhook'
    _description = 'Shopify Webhook'
    _order = 'store_id, topic'

    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    topic = fields.Char(required=True)
    shopify_gid = fields.Char(string='Shopify ID')
    uri = fields.Char(string='Address')

    _store_topic_unique = models.Constraint('unique (store_id, topic)', "A store has one webhook per topic.")
