from odoo import Command
from odoo.tests import tagged

from .common import item, mock_woo, order, tax_line
from .test_order import WooOrderCase


@tagged('post_install', '-at_install')
class TestRefunds(WooOrderCase):

    def paid_order(self, **extra):
        return order(items=[item(1, 10, 2, 20, taxes=[(1, 2.0)])], tax_lines=[tax_line(1, 10.0)], total=22.0, **extra)

    def test_refund_becomes_paid_credit_note(self):
        sale = self._sync(self.paid_order())
        refund = {'id': 501, 'amount': '11.00', 'reason': 'Broken', 'refunded_payment': True, 'shipping_lines': [],
                  'line_items': [{'id': 601, 'product_id': 10, 'variation_id': 0, 'quantity': -1, 'total': '-10.00',
                                  'meta_data': [{'key': '_refunded_item_id', 'value': '1'}]}]}
        data = self.paid_order(status='processing', refunds=[{'id': 501, 'reason': 'Broken', 'total': '-11.00'}])
        sale = self._sync(data, {'GET orders/1001/refunds/501': refund})
        credit_note = sale.invoice_ids.filtered(lambda m: m.move_type == 'out_refund')
        self.assertEqual(credit_note.state, 'posted')
        self.assertEqual(credit_note.amount_total, 11.0)
        self.assertEqual(credit_note.woo_refund_id, '501')
        self.assertIn(credit_note.payment_state, ('paid', 'in_payment'))
        self.assertEqual(sale.order_line.product_uom_qty, 1, "the refunded mug leaves the order")
        sale = self._sync(data, {'GET orders/1001/refunds/501': refund})
        self.assertEqual(len(sale.invoice_ids.filtered(lambda m: m.move_type == 'out_refund')), 1, "imported once")
        self.assertEqual(len(sale.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice')), 1,
                         "not invoiced again")

    def test_refund_with_return(self):
        self.env['stock.quant']._update_available_quantity(self.mug, self.store.warehouse_id.lot_stock_id, 10)
        self.store.write({'refund_create_return': True, 'refund_validate_return': True})
        sale = self._sync(self.paid_order(status='completed'))
        self.assertEqual(sale.picking_ids.state, 'done')
        refund = {'id': 502, 'amount': '22.00', 'line_items': [
            {'id': 602, 'product_id': 10, 'variation_id': 0, 'quantity': -2, 'total': '-20.00', 'meta_data': []}]}
        sale = self._sync(self.paid_order(status='refunded', refunds=[{'id': 502, 'total': '-22.00'}]),
                          {'GET orders/1001/refunds/502': refund})
        returns = sale.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming')
        self.assertEqual(returns.state, 'done')
        self.assertEqual(returns.move_ids.quantity, 2, "found by its product")

    def test_credit_note_refunded_in_woocommerce(self):
        self.store.refund_api = True
        sale = self._sync(self.paid_order())
        line = sale.order_line
        credit_note = sale._connector_credit_note([(line, 1)], 11.0, 'Return')
        self.assertEqual(credit_note.woo_order_id, sale)
        credit_note.action_woo_refund()
        job = self.env['om.connector.job'].search([('method_name', '=', '_connector_job_woo_refund')])
        with mock_woo({'GET orders/1001': self.paid_order(),
                       'POST orders/1001/refunds': lambda params, body: {'id': 777, **body}}) as fake:
            job.action_run_now()
        self.assertEqual(job.state, 'done', job.error)
        body = fake.bodies('POST orders/1001/refunds')[0]
        self.assertEqual(body['amount'], '11.00')
        self.assertTrue(body['api_refund'])
        self.assertEqual(body['line_items'], [{'id': 1, 'quantity': 1.0, 'refund_total': 10.0,
                                               'refund_tax': [{'id': 1, 'refund_total': 1.0}]}])
        self.assertEqual(credit_note.woo_refund_id, '777')
        # the order.updated webhook that follows does not import it again
        data = self.paid_order(refunds=[{'id': 777, 'total': '-11.00'}])
        self._sync(data)
        self.assertEqual(len(sale.invoice_ids.filtered(lambda m: m.move_type == 'out_refund')), 1)

    def test_cancel_in_woocommerce(self):
        sale = self._sync(order(status='on-hold', paid=False, items=[item(1, 10, 1, 10)], total=10))
        wizard = self.env['om.woocommerce.cancel.wizard'].create({'order_id': sale.id, 'note': 'Out of stock'})
        with mock_woo({'POST orders/1001/notes': {'id': 1},
                       'PUT orders/1001': lambda params, body: {'id': 1001, **body}}) as fake:
            wizard.action_cancel()
        self.assertEqual(fake.bodies('PUT orders/1001'), [{'status': 'cancelled'}])
        self.assertEqual(sale.state, 'cancel')
        self.assertEqual(sale.woo_status, 'cancelled')
        self.assertTrue(Command)
