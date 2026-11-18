from odoo import fields, models


class OmWoocommerceWebhook(models.Model):
    """ A webhook of a store, made by Odoo in WooCommerce. """
    _name = 'om.woocommerce.webhook'
    _description = 'WooCommerce Webhook'
    _order = 'store_id, topic'

    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    topic = fields.Char(required=True)
    woo_id = fields.Char(string='WooCommerce ID')
    delivery_url = fields.Char(string='Address')
    status = fields.Selection([('active', 'Active'), ('paused', 'Paused'), ('disabled', 'Disabled')],
                              help="WooCommerce disables a webhook after repeated failed deliveries: click Sync "
                                   "Webhooks on the store to turn it on again.")

    _sql_constraints = [
        ('store_topic_unique', 'unique (store_id, topic)',
         "A store has one webhook per topic."),
    ]
