from odoo.exceptions import UserError
from odoo.tests import HttpCase, JsonRpcException, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.flow_visualizer.models.tracer import CURRENT, Tracer


@tagged('post_install', '-at_install')
class TestFlowVisualizer(HttpCase):

    def setUp(self):
        super().setUp()
        # traces left by people using the database are not this test's
        self.env['flow.visualizer.trace'].search([]).unlink()
        self.authenticate('admin', 'admin')

    def _call(self, model, method, args, kwargs=None, route='call_kw'):
        return self.make_jsonrpc_request(f'/web/dataset/{route}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {},
        })

    def _traces(self):
        return self.make_jsonrpc_request('/flow_visualizer/traces', {})

    def _walk(self, nodes):
        for node in nodes:
            yield node
            yield from self._walk(node.get('children', []))

    def test_nothing_is_traced_while_off(self):
        self._call('res.partner', 'create', [[{'name': 'Untraced'}]])
        self.assertEqual(self._traces(), [])

    def test_a_create_is_traced_with_its_records(self):
        self.make_jsonrpc_request('/flow_visualizer/toggle', {'enabled': True})
        [partner_id] = self._call('res.partner', 'create', [[{
            'name': 'Flow Company', 'is_company': True,
            'child_ids': [(0, 0, {'name': 'Flow Contact'})],
        }]])
        [trace] = self._traces()
        self.assertEqual(trace['state'], 'done')
        self.assertEqual(trace['name'], 'res.partner.create')
        created = [node for node in self._walk(trace['tree'])
                   if node['kind'] == 'create' and node['model'] == 'res.partner']
        records = {record[1]: record for node in created for record in node['records']}
        self.assertIn('Flow Company', records)
        self.assertEqual(records['Flow Company'][0], partner_id)
        self.assertTrue(records['Flow Company'][2], "an existing record can be opened")
        self.assertTrue(any(name.endswith('Flow Contact') for name in records))

    def test_a_write_shows_the_values_before_and_after(self):
        partner = self.env['res.partner'].create({'name': 'Before Name'})
        self.make_jsonrpc_request('/flow_visualizer/toggle', {'enabled': True})
        self._call('res.partner', 'write', [[partner.id], {'name': 'After Name'}])
        [trace] = self._traces()
        [write] = [node for node in self._walk(trace['tree']) if node['kind'] == 'write']
        self.assertIn(['Name', 'Before Name', 'After Name', 'name'], write['changes'][0]['lines'])

    def test_reads_are_not_traced(self):
        self.make_jsonrpc_request('/flow_visualizer/toggle', {'enabled': True})
        self._call('res.partner', 'search_read', [[]], {'fields': ['name'], 'limit': 5})
        self._call('res.partner', 'web_search_read', [[]], {'specification': {'name': {}}, 'limit': 5})
        self.assertEqual(self._traces(), [])

    def test_a_delete_keeps_the_name(self):
        partner = self.env['res.partner'].create({'name': 'Gone Soon'})
        self.make_jsonrpc_request('/flow_visualizer/toggle', {'enabled': True})
        self._call('res.partner', 'unlink', [[partner.id]])
        [trace] = self._traces()
        [unlink] = [node for node in self._walk(trace['tree'])
                    if node['kind'] == 'unlink' and node['model'] == 'res.partner']
        self.assertEqual(unlink['records'], [[partner.id, 'Gone Soon', False]])

    def test_a_failed_call_is_kept_as_rolled_back(self):
        # the trace is written on a cursor of its own; in tests every cursor
        # shares the test transaction, which the failed request rolls back:
        # the tracer is driven here as the controller drives it
        tracer = Tracer(self.env, 'res.partner', 'action_x', [[1]])
        token = CURRENT.set(tracer)
        try:
            self.env['res.partner'].create({'name': 'Rolled Back'})
        finally:
            CURRENT.reset(token)
        tracer.finish(self.env, UserError("Nothing is saved"))
        trace = self.env['flow.visualizer.trace'].search([('name', '=', 'res.partner.action_x')])
        self.assertEqual(trace.state, 'failed')
        self.assertEqual(trace.error, "Nothing is saved")
        self.assertEqual(trace.tree[0]['kind'], 'create')

    @mute_logger('odoo.http')
    def test_a_failed_request_still_fails(self):
        partner = self.env['res.partner'].create({'name': 'Loop'})
        self.make_jsonrpc_request('/flow_visualizer/toggle', {'enabled': True})
        with self.assertRaises(JsonRpcException):
            self._call('res.partner', 'write', [[partner.id], {'parent_id': partner.id}])

    @mute_logger('odoo.http')
    def test_only_administrators_trace(self):
        new_test_user(self.env, 'flow_user', groups='base.group_user', password='flow-user-pw')
        self.authenticate('flow_user', 'flow-user-pw')
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/flow_visualizer/toggle', {'enabled': True})

    def test_panel_shows_a_click_and_opens_its_record(self):
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
            (await until('.o_flow_systray')).click();
            await until('.o_flow_panel');
            const { rpc } = odoo.loader.modules.get('@web/core/network/rpc');
            await rpc('/web/dataset/call_kw/res.partner/create', {
                model: 'res.partner', method: 'create', args: [[{name: 'Panel Partner'}]], kwargs: {},
            });
            await until('.o_flow_kind_create .o_flow_card_name', 'Panel Partner');
            (await until('.o_flow_tab_technical')).click();
            (await until('.o_flow_create .o_flow_chip', 'Panel Partner')).click();
            await until('.o_form_view .o_field_widget[name=name] input');
            const input = document.querySelector('.o_form_view .o_field_widget[name=name] input');
            if (input.value !== 'Panel Partner') {
                throw new Error(`the chip opened ${input.value}`);
            }
            console.log('test successful');
        })().catch((error) => console.error(error.message));"""
        self.browser_js('/odoo', code, login='admin', timeout=90)
