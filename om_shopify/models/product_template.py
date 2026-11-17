from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    shopify_binding_ids = fields.One2many('om.shopify.product.template', 'product_tmpl_id', string='Shopify Products')
    shopify_binding_count = fields.Integer(compute='_compute_shopify_binding_count', string='In Shopify')

    def _compute_shopify_binding_count(self):
        for template in self:
            template.shopify_binding_count = len(template.shopify_binding_ids)
