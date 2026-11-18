from odoo import fields, models


class OmWoocommerceOrderStatus(models.Model):
    """ A status of the WooCommerce orders. The statuses of WooCommerce are given; the custom statuses
    of an extension can be added with their code. """
    _name = 'om.woocommerce.order.status'
    _description = 'WooCommerce Order Status'
    _order = 'sequence, id'
    _rec_name = 'name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help="The status in WooCommerce, without the wc- prefix (processing, on-hold…).")
    sequence = fields.Integer(default=10)

    _code_unique = models.Constraint('unique (code)', "An order status is listed once.")
