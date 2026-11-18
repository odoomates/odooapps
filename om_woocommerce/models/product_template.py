from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    woo_binding_ids = fields.One2many('om.woocommerce.product.template', 'product_tmpl_id',
                                      string='WooCommerce Products')
