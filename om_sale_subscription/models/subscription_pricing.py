from odoo import api, fields, models


class OmSubscriptionPricing(models.Model):
    _name = 'om.subscription.pricing'
    _description = 'Recurring Price'
    _order = 'product_tmpl_id, plan_id, pricelist_id'

    product_tmpl_id = fields.Many2one('product.template', string='Product', required=True, ondelete='cascade',
                                      index=True)
    product_id = fields.Many2one('product.product', string='Variant', ondelete='cascade',
                                 domain="[('product_tmpl_id', '=', product_tmpl_id)]",
                                 help='Leave empty to use this price for all variants.')
    plan_id = fields.Many2one('om.subscription.plan', string='Recurring Plan', required=True, ondelete='cascade',
                              index=True)
    pricelist_id = fields.Many2one('product.pricelist', ondelete='cascade',
                                   help='Leave empty to use this price with any pricelist.')
    company_id = fields.Many2one(related='product_tmpl_id.company_id')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True, readonly=False, precompute=True,
                                  required=True)
    price = fields.Monetary(string='Recurring Price', required=True, currency_field='currency_id')

    @api.depends('pricelist_id', 'product_tmpl_id')
    def _compute_currency_id(self):
        for pricing in self:
            pricing.currency_id = (pricing.pricelist_id.currency_id or pricing.product_tmpl_id.currency_id
                                   or self.env.company.currency_id)

    @api.model
    def _get_best_pricing(self, product, plan, pricelist=False):
        """Most specific price of `product` for `plan`: variant before template, pricelist before none."""
        if not product or not plan:
            return self.browse()
        pricings = product.product_tmpl_id.subscription_pricing_ids.filtered(
            lambda p: p.plan_id == plan
            and (not p.product_id or p.product_id == product)
            and (not p.pricelist_id or p.pricelist_id == pricelist)
        )
        return pricings.sorted(lambda p: (not p.product_id, not p.pricelist_id))[:1]
