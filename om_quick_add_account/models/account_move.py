from odoo import api, models
from odoo.fields import Domain
from odoo.tools.sql import escape_like_value

from odoo.addons.om_quick_add.models.quick_add_mixin import HISTORY_LINES


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'om.quick.add.mixin']

    _om_qa_line_field = 'invoice_line_ids'
    _om_qa_quantity_field = 'quantity'

    @api.model
    def _om_qa_copy_label(self):
        return self.env._("Invoice or Bill")

    def _om_qa_editable(self):
        return self.state == 'draft' and self.is_invoice(include_receipts=True)

    def _om_qa_partner(self):
        return self.commercial_partner_id

    def _om_qa_product_domain(self):
        domain = super()._om_qa_product_domain()
        if self.is_sale_document(include_receipts=True):
            return domain & Domain('sale_ok', '=', True)
        if self.is_purchase_document(include_receipts=True):
            return domain & Domain('purchase_ok', '=', True)
        return domain

    def _om_qa_code_domain(self, code):
        partner = self._om_qa_partner()
        if not partner or not self.is_purchase_document(include_receipts=True):
            return None
        return Domain('product_tmpl_id.seller_ids', 'any', [
            ('partner_id', 'child_of', partner.id), ('product_code', '=ilike', escape_like_value(code))])

    def _om_qa_bar_price(self, product):
        if self.is_purchase_document(include_receipts=True):
            seller = product._select_seller(partner_id=self.partner_id, quantity=1.0, uom_id=product.uom_id)
            return seller.price if seller else product.standard_price
        return product.lst_price

    def _om_qa_lines(self):
        return self.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.product_id)

    def _om_qa_line_data(self, line):
        move = line.move_id
        return {
            'product': line.product_id,
            'quantity': line.quantity,
            'uom': line.product_uom_id,
            'price_unit': line.price_unit,
            'discount': line.discount,
            'date': move.invoice_date or move.date,
            'document': move,
        }

    def _om_qa_new_line_vals(self, product, quantity, uom, price_unit, discount):
        vals = {'product_id': product.id, 'quantity': quantity}
        if uom:
            vals['product_uom_id'] = uom.id
        if price_unit is not None:
            vals['price_unit'] = price_unit
        if discount is not None:
            vals['discount'] = discount
        return vals

    def _om_qa_history_lines(self):
        if self.is_sale_document(include_receipts=True):
            move_types = ['out_invoice', 'out_receipt']
        elif self.is_purchase_document(include_receipts=True):
            move_types = ['in_invoice', 'in_receipt']
        else:
            return self.env['account.move.line']
        return self.env['account.move.line'].search([
            ('move_id.commercial_partner_id', '=', self._om_qa_partner().id),
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', 'in', move_types),
            ('move_id', '!=', self.id or False),
            ('company_id', '=', self.company_id.id),
            ('display_type', '=', 'product'),
            ('product_id', '!=', False),
        ], order='id desc', limit=HISTORY_LINES)


class AccountMoveLine(models.Model):
    _name = 'account.move.line'
    _inherit = ['account.move.line', 'om.quick.add.line.mixin']

    _om_qa_document_model = 'account.move'
