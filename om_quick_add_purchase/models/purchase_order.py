from odoo import models
from odoo.fields import Domain
from odoo.tools.sql import escape_like_value

from odoo.addons.om_quick_add.models.quick_add_mixin import HISTORY_LINES


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'om.quick.add.mixin']

    _om_qa_line_field = 'order_line'
    _om_qa_quantity_field = 'product_qty'

    def _om_qa_editable(self):
        return self.state != 'cancel' and not self.locked

    def _om_qa_partner(self):
        return self.partner_id.commercial_partner_id

    def _om_qa_product_domain(self):
        return super()._om_qa_product_domain() & Domain('purchase_ok', '=', True)

    def _om_qa_code_domain(self, code):
        partner = self._om_qa_partner()
        if not partner:
            return None
        # the code the vendor gives the product
        return Domain('product_tmpl_id.seller_ids', 'any', [
            ('partner_id', 'child_of', partner.id), ('product_code', '=ilike', escape_like_value(code))])

    def _om_qa_bar_price(self, product):
        seller = product._select_seller(partner_id=self.partner_id, quantity=1.0, uom_id=product.uom_id)
        return seller.price if seller else product.standard_price

    def _om_qa_lines(self):
        return self.order_line.filtered(lambda l: l.product_id and not l.display_type and not l.is_downpayment)

    def _om_qa_line_data(self, line):
        order = line.order_id
        date = order.date_approve or order.date_order
        return {
            'product': line.product_id,
            'quantity': line.product_qty,
            'uom': line.uom_id,
            'price_unit': line.price_unit,
            'discount': line.discount,
            'date': date and date.date(),
            'document': order,
        }

    def _om_qa_new_line_vals(self, product, quantity, uom, price_unit, discount):
        vals = {'product_id': product.id, 'product_qty': quantity}
        if uom:
            vals['uom_id'] = uom.id
        if price_unit is not None:
            vals['price_unit'] = price_unit
        if discount is not None:
            vals['discount'] = discount
        return vals

    def _om_qa_history_lines(self):
        partner = self._om_qa_partner()
        return self.env['purchase.order.line'].search([
            ('order_id.partner_id', 'child_of', partner.id),
            ('state', '=', 'purchase'),
            ('order_id', '!=', self.id or False),
            ('company_id', '=', self.company_id.id),
            ('display_type', '=', False),
            ('product_id', '!=', False),
            ('is_downpayment', '=', False),
        ], order='id desc', limit=HISTORY_LINES)


class PurchaseOrderLine(models.Model):
    _name = 'purchase.order.line'
    _inherit = ['purchase.order.line', 'om.quick.add.line.mixin']

    _om_qa_document_model = 'purchase.order'
