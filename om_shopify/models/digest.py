from odoo import fields, models


class DigestDigest(models.Model):
    _inherit = 'digest.digest'

    kpi_om_shopify_orders = fields.Boolean(string='Shopify Orders')
    kpi_om_shopify_orders_value = fields.Integer(compute='_compute_kpi_om_shopify_orders_value')

    def _compute_kpi_om_shopify_orders_value(self):
        self._calculate_kpi('sale.order', 'kpi_om_shopify_orders_value', date_field='date_order',
                            additional_domain=[('shopify_store_id', '!=', False), ('state', '=', 'sale')])

    def _get_kpi_custom_settings(self, company, user):
        res = super()._get_kpi_custom_settings(company, user)
        menu = self.env.ref('om_shopify.om_shopify_menu_root', raise_if_not_found=False)
        res['kpi_action']['kpi_om_shopify_orders'] = 'om_shopify.om_shopify_sale_order_action' + (
            f'?menu_id={menu.id}' if menu else '')
        res['kpi_sequence']['kpi_om_shopify_orders'] = 2600
        return res
