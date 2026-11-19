from odoo import models
from odoo.fields import Domain

from odoo.addons.om_quick_add.models.quick_add_mixin import HISTORY_LINES


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'om.quick.add.mixin']

    _om_qa_line_field = 'order_line'
    _om_qa_quantity_field = 'product_uom_qty'

    def _om_qa_editable(self):
        return self.state != 'cancel' and not self.locked

    def _om_qa_partner(self):
        return self.partner_id.commercial_partner_id

    def _om_qa_product_domain(self):
        return super()._om_qa_product_domain() & Domain('sale_ok', '=', True)

    def _om_qa_bar_price(self, product):
        if self.pricelist_id:
            return self.pricelist_id._get_product_price(product, 1.0, currency=self.currency_id)
        return product.lst_price

    def _om_qa_lines(self):
        return self.order_line.filtered(lambda l: l.product_id and not l.display_type and not l.is_downpayment)

    def _om_qa_line_data(self, line):
        order = line.order_id
        return {
            'product': line.product_id,
            'quantity': line.product_uom_qty,
            'uom': line.product_uom_id,
            'price_unit': line.price_unit,
            'discount': line.discount,
            'date': order.date_order and order.date_order.date(),
            'document': order,
        }

    def _om_qa_new_line_vals(self, product, quantity, uom, price_unit, discount):
        vals = {'product_id': product.id, 'product_uom_qty': quantity}
        if uom:
            vals['product_uom_id'] = uom.id
        if price_unit is not None:
            vals['price_unit'] = price_unit
        if discount is not None:
            vals['discount'] = discount
        return vals

    def _om_qa_history_lines(self):
        partner = self._om_qa_partner()
        return self.env['sale.order.line'].search([
            ('order_id.partner_id', 'child_of', partner.id),
            ('state', '=', 'sale'),
            ('order_id', '!=', self.id or False),
            ('company_id', '=', self.company_id.id),
            ('display_type', '=', False),
            ('product_id', '!=', False),
            ('is_downpayment', '=', False),
        ], order='id desc', limit=HISTORY_LINES)


class SaleOrderLine(models.Model):
    _name = 'sale.order.line'
    _inherit = ['sale.order.line', 'om.quick.add.line.mixin']

    _om_qa_document_model = 'sale.order'
