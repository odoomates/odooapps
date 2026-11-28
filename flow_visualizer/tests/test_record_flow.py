from markupsafe import Markup

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestRecordFlow(HttpCase):
    """ The flow of a sales order, from the quotation to its payment. Runs where
    Sales, Inventory and Invoicing are installed. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'sale.order' not in cls.env or 'stock.picking' not in cls.env:
            cls.skipTest(cls, "needs sale_stock")
        env = cls.env
        product = env['product.product'].create({
            'name': 'Flow Chair', 'is_storable': True, 'invoice_policy': 'delivery', 'list_price': 100,
        })
        env['stock.quant']._update_available_quantity(product, env.ref('stock.stock_location_stock'), 10)
        partner = env['res.partner'].create({'name': 'Flow Customer'})
        cls.order = env['sale.order'].create({
            'partner_id': partner.id, 'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 2})],
        })
        cls.order.action_confirm()
        cls.picking = cls.order.picking_ids
        cls.picking.move_ids.quantity = 2
        cls.picking.move_ids.picked = True
        cls.picking.with_context(skip_sms=True, skip_backorder=True).button_validate()
        cls.invoice = cls.order._create_invoices()
        cls.invoice.action_post()
        env['account.payment.register'].with_context(
            active_model='account.move', active_ids=cls.invoice.ids).create({})._create_payments()

    def test_the_flow_follows_the_order_to_its_payment(self):
        flow = self.env['flow.visualizer.record'].flow_of('sale.order', self.order.id)
        keys = {card['key'] for card in flow['documents']}
        self.assertIn(f'sale.order,{self.order.id}', keys)
        self.assertIn(f'stock.picking,{self.picking.id}', keys)
        self.assertIn(f'account.move,{self.invoice.id}', keys)
        self.assertTrue(any(key.startswith('account.payment,') for key in keys), "the payment is found")
        self.assertFalse(
            [card for card in flow['documents'] if card['model'] == 'account.move' and card['id'] != self.invoice.id],
            "the accounting entry of the payment is left out")
        delivery = next(card for card in flow['documents'] if card['model'] == 'stock.picking')
        self.assertEqual(delivery['state'][0], 'done')
        self.assertIn('date_done', [milestone['field'] for milestone in delivery['milestones']])
        invoice = next(card for card in flow['documents'] if card['model'] == 'account.move')
        self.assertIn(invoice['payment_state'][0], ('paid', 'in_payment'))

    def test_the_flow_reads_status_changes_from_the_chatter(self):
        body = Markup('<div>Quotation → <b>Sales Order</b> <i>(Status)</i></div>')
        self.order.message_post(body=body, message_type='tracking')
        flow = self.env['flow.visualizer.record'].flow_of('sale.order', self.order.id)
        changes = [event for event in flow['events'] if event['kind'] == 'status']
        self.assertIn(('Quotation', 'Sales Order'), [(event['old'], event['new']) for event in changes])

    def test_show_flow_from_the_gear_menu(self):
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector, text) => {
                for (let tries = 0; tries < 75; tries++) {
                    const found = [...document.querySelectorAll(selector)].find(
                        (element) => !text || element.textContent.includes(text));
                    if (found) {
                        return found;
                    }
                    await wait(200);
                }
                throw new Error(`not found: ${selector} ${text || ''}`);
            };
            (await until('.o_cp_action_menus button, .o_form_view .o_cp_action_menus .dropdown-toggle')).click();
            (await until('.o_flow_record_menu')).click();
            await until('.o_flow_record_dialog .o_flow_station');
            await until('.o_flow_station_name', '%(picking)s');
            await until('.o_flow_station_name', '%(invoice)s');
            await until('.o_flow_event');
            (await until('.o_flow_station_name', '%(picking)s')).click();
            await until('.o_breadcrumb', '%(picking)s');
            console.log('test successful');
        })().catch((error) => console.error(error.message));""" % {
            'picking': self.picking.name, 'invoice': self.invoice.name,
        }
        self.browser_js(f'/odoo/action-sale.action_orders/{self.order.id}', code, login='admin', timeout=90)

    def test_the_story_of_a_confirm_tells_the_delivery(self):
        quotation = self.order.copy()
        self.env['flow.visualizer.trace'].search([]).unlink()
        self.authenticate('admin', 'admin')
        self.make_jsonrpc_request('/flow_visualizer/toggle', {'enabled': True})
        self.make_jsonrpc_request('/web/dataset/call_button', {
            'model': 'sale.order', 'method': 'action_confirm', 'args': [[quotation.id]], 'kwargs': {},
        })
        [trace] = self.make_jsonrpc_request('/flow_visualizer/traces', {})
        story = trace['story']
        self.assertEqual(story['action'], 'Confirm')
        cards = {card['model']: card for card in story['documents']}
        self.assertEqual(cards['sale.order']['kind'], 'clicked')
        self.assertEqual(cards['sale.order']['state_before'], 'Quotation')
        delivery = cards['stock.picking']
        self.assertEqual(delivery['kind'], 'create')
        self.assertEqual(delivery['parent'], f'sale.order,{quotation.id}')
        moves = next(group for group in delivery['lines'] if group['model'] == 'stock.move')
        self.assertIn('Flow Chair × 2', moves['items'])

    def test_back_to_the_delivery_plans_the_payment_then_the_invoice(self):
        plan = self.env['flow.visualizer.record'].rewind_plan(
            'sale.order', self.order.id, f'stock.picking,{self.picking.id}')
        self.assertEqual([item['model'] for item in plan], ['account.payment', 'account.move'],
                         "the newest first: the payment, then its invoice")
        self.assertEqual(plan[0]['steps'], ['Reset to draft', 'Cancel'])
        self.assertEqual(plan[1]['steps'], ['Reset to draft', 'Cancel'])
        self.assertFalse(any(item['blocked'] for item in plan))

    def test_back_to_the_delivery(self):
        payment = self.invoice.matched_payment_ids
        done = self.env['flow.visualizer.record'].rewind_apply(
            'sale.order', self.order.id, f'stock.picking,{self.picking.id}')
        self.assertTrue(done)
        self.assertEqual(self.invoice.state, 'cancel')
        self.assertEqual(payment.state, 'canceled')
        self.assertEqual(self.picking.state, 'done', "the delivery stays as it was")
        # and a new invoice can be made, left unpaid
        new_invoice = self.order._create_invoices()
        new_invoice.action_post()
        self.assertEqual(new_invoice.payment_state, 'not_paid')

    def test_a_done_delivery_is_blocked(self):
        plan = self.env['flow.visualizer.record'].rewind_plan(
            'sale.order', self.order.id, f'sale.order,{self.order.id}')
        delivery = next(item for item in plan if item['model'] == 'stock.picking')
        self.assertIn('return', delivery['blocked'])
