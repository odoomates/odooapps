from odoo import fields, models

FINANCIAL_STATUSES = [
    ('PAID', 'Paid'),
    ('PENDING', 'Pending'),
    ('AUTHORIZED', 'Authorized'),
    ('PARTIALLY_PAID', 'Partially Paid'),
    ('PARTIALLY_REFUNDED', 'Partially Refunded'),
    ('REFUNDED', 'Refunded'),
    ('VOIDED', 'Voided'),
    ('EXPIRED', 'Expired'),
]
FULFILLMENT_STATUSES = [
    ('UNFULFILLED', 'Unfulfilled'),
    ('PARTIALLY_FULFILLED', 'Partially Fulfilled'),
    ('FULFILLED', 'Fulfilled'),
]


class OmShopifyOrderRule(models.Model):
    """ What an imported order gets when it matches: a workflow, a warehouse, or both. The first
    rule that matches gives each of them; what no rule gives comes from the payment method, then
    from the store. Covers for example "paid by cash on delivery: no payment", or "tagged prime:
    shipped from the Amazon warehouse". """
    _name = 'om.shopify.order.rule'
    _description = 'Shopify Order Rule'
    _order = 'store_id, sequence, id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    gateway_id = fields.Many2one('om.shopify.gateway', string='Payment Method', check_company=True,
                                 domain="[('store_id', '=', store_id)]", help="Empty: any payment method.")
    financial_status = fields.Selection(FINANCIAL_STATUSES, string='Payment Status', help="Empty: any.")
    fulfillment_status = fields.Selection(FULFILLMENT_STATUSES, string='Fulfillment Status', help="Empty: any.")
    tag = fields.Char(help="The order has this tag in Shopify. Empty: any.")
    source = fields.Char(string='Sales Channel', help="Source of the order in Shopify: web, pos, shopify_draft_order… "
                                                      "Empty: any.")
    workflow_id = fields.Many2one('om.connector.order.workflow', string='Workflow', check_company=True)
    warehouse_id = fields.Many2one('stock.warehouse', check_company=True)

    def _matches(self, data, gateway):
        self.ensure_one()
        tags = {t.lower() for t in data.get('tags') or []}
        return (
            (not self.gateway_id or self.gateway_id == gateway)
            and (not self.financial_status or self.financial_status == data.get('displayFinancialStatus'))
            and (not self.fulfillment_status or self.fulfillment_status == data.get('displayFulfillmentStatus'))
            and (not self.tag or self.tag.lower() in tags)
            and (not self.source or self.source.lower() == (data.get('sourceName') or '').lower())
        )
