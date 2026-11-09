from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _om_pos_cashier(self, order):
        """ (user, employee) who sent this order: om_pos_access_hr knows the employee. """
        return self.env.user, None

    @api.model
    def _om_pos_lines(self, order):
        """ The values of the lines of an order sent by the shop. """
        return [line[2] for line in order.get('lines') or ()
                if isinstance(line, (list, tuple)) and len(line) > 2 and isinstance(line[2], dict)]

    @api.model
    def _om_pos_check(self, order, rules):
        """ Refuse what the rules of the cashier do not allow in this order. """
        Access = self.env['om.pos.access']
        lines = self._om_pos_lines(order)
        flags = rules['flags']
        # money given back: a line of a receipt refunded, or a line made negative by hand
        returned = [line for line in lines if (line.get('qty') or 0) < 0
                    and not line.get('reward_id') and not line.get('is_reward_line') and not line.get('combo_parent_id')]
        by_hand = [line for line in returned if not line.get('refunded_orderline_id')]
        if 'refund' in flags and (order.get('is_refund') or returned
                                  or any(line.get('refunded_orderline_id') for line in lines)):
            raise UserError(Access._om_pos_message('refund'))
        if 'refund_receipt' in flags and by_hand:
            raise UserError(Access._om_pos_message('refund_receipt'))
        session = self.env['pos.session'].sudo().browse(order.get('session_id')).exists()
        config = session.config_id
        currency = config.currency_id or self.env.company.currency_id
        if rules.get('max_refund') and returned:
            refunded = sum(abs(line['price_subtotal_incl']) if line.get('price_subtotal_incl') is not None
                           else abs((line.get('qty') or 0) * (line.get('price_unit') or 0)
                                    * (1 - (line.get('discount') or 0) / 100))
                           for line in returned)
            if currency.compare_amounts(refunded, rules['max_refund']) > 0:
                raise UserError(Access._om_pos_message('max_refund', limit=currency.format(rules['max_refund'])))
        if rules.get('pricelists') is not None and order.get('pricelist_id') \
                and order['pricelist_id'] not in rules['pricelists']:
            pricelist = self.env['product.pricelist'].sudo().browse(order['pricelist_id'])
            raise UserError(Access._om_pos_message('pricelist', pricelist=pricelist.display_name))
        if rules['payment_methods'] is not None:
            for payment in order.get('payment_ids') or ():
                values = payment[2] if isinstance(payment, (list, tuple)) and len(payment) > 2 else None
                method_id = isinstance(values, dict) and values.get('payment_method_id')
                if method_id and method_id not in rules['payment_methods']:
                    method = self.env['pos.payment.method'].sudo().browse(method_id)
                    raise UserError(Access._om_pos_message('payment_method', method=method.display_name))
        skipped = {product.id for product in (
            config._fields.get('discount_product_id') and config.discount_product_id,
            config._fields.get('tip_product_id') and config.tip_product_id) if product}
        pricelist = self.env['product.pricelist'].sudo().browse(order.get('pricelist_id')).exists() \
            or config.pricelist_id
        for line in lines:
            # a refund repeats the sale it refunds; combo parts, rewards and fees have computed prices
            if line.get('refunded_orderline_id') or line.get('combo_parent_id') or line.get('reward_id'):
                continue
            discount = line.get('discount') or 0
            if line.get('product_id') in skipped:
                if 'discount' in flags and line.get('product_id') == (
                        config._fields.get('discount_product_id') and config.discount_product_id.id):
                    raise UserError(Access._om_pos_message('discount'))
                continue
            if discount > 0 and 'discount' in flags:
                raise UserError(Access._om_pos_message('discount'))
            if rules['max_discount'] and float_compare(discount, rules['max_discount'], precision_digits=2) > 0:
                raise UserError(Access._om_pos_message('max_discount', limit=rules['max_discount']))
            product = self.env['product.product'].sudo().browse(line.get('product_id')).exists()
            price = line.get('price_unit')
            if not product or price is None or (line.get('qty') or 0) <= 0:
                continue
            if 'price' in flags or rules['max_price_cut']:
                reference = pricelist._get_product_price(product, line.get('qty') or 1.0) if pricelist \
                    else product.lst_price
                floor = reference * (1 - (0 if 'price' in flags else rules['max_price_cut']) / 100)
                if currency.compare_amounts(price, floor) < 0:
                    raise UserError(Access._om_pos_message(
                        'price' if 'price' in flags else 'max_price_cut', **(
                            {} if 'price' in flags else {'limit': rules['max_price_cut']})))
            if 'below_cost' in flags and product.standard_price and currency.compare_amounts(
                    price * (1 - discount / 100), product.standard_price) < 0:
                raise UserError(Access._om_pos_message('below_cost', product=product.display_name))

    @api.model
    def sync_from_ui(self, orders):
        Access = self.env['om.pos.access']
        for order in orders:
            user, employee = self._om_pos_cashier(order)
            rules = Access._om_pos_rules(user, employee)
            if not Access._om_pos_empty(rules):
                self._om_pos_check(order, rules)
        return super().sync_from_ui(orders)

    @api.model
    def _om_pos_cancel_cashier(self):
        """ (user, employee) cancelling orders from the shop: om_pos_access_hr knows the employee. """
        return self.env.user, None

    def cancel_order_from_pos(self):
        # an order with products only: the shop also drops empty orders this way
        if self.filtered(lambda order: order.state == 'draft' and order.lines):
            Access = self.env['om.pos.access']
            if Access._om_pos_refuse('cancel', *self._om_pos_cancel_cashier()):
                raise UserError(Access._om_pos_message('cancel'))
        return super().cancel_order_from_pos()
