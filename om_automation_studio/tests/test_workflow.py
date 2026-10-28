from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import WorkflowCase, chain, node
from odoo.addons.om_automation_studio.tools import check_graph


@tagged('post_install', '-at_install')
class TestWorkflow(WorkflowCase):

    def test_default_graph(self):
        workflow = self.Workflow.create({'name': 'Empty', 'model_id': self.partner_model.id})
        self.assertEqual([n['type'] for n in workflow.graph['nodes']], ['start', 'end'])
        self.assertEqual(workflow.state, 'draft')
        self.assertFalse([i for i in check_graph(self.env, 'res.partner', workflow.graph) if i['level'] == 'error'])

    def test_check_graph(self):
        graph = chain(
            node('s', 'start', trigger='create'),
            node('c', 'condition', domain='[]'),
            node('u', 'update', values=[{'field': 'nope', 'mode': 'value', 'value': 1}]),
            node('m', 'email', template_id=False),
        )
        graph['nodes'].append(node('lost', 'note', body='hello'))
        issues = check_graph(self.env, 'res.partner', graph)
        by_node = {}
        for issue in issues:
            by_node.setdefault(issue['node'], []).append(issue['level'])
        self.assertIn('error', by_node['c'])
        self.assertIn('error', by_node['u'])
        self.assertIn('error', by_node['m'])
        self.assertEqual(by_node['lost'], ['warning'])

        two_starts = chain(node('s', 'start', trigger='create'), node('s2', 'start', trigger='create'))
        self.assertTrue(any(not i['node'] for i in check_graph(self.env, 'res.partner', two_starts)))

    def test_loop_without_wait(self):
        graph = chain(
            node('s', 'start', trigger='create'),
            node('a', 'note', body='a'),
            node('b', 'note', body='b'),
            branches=[('b', 'out', 'a')],
        )
        self.assertTrue(any('loop' in i['message'] for i in check_graph(self.env, 'res.partner', graph)))
        graph = chain(
            node('s', 'start', trigger='create'),
            node('a', 'note', body='a'),
            node('w', 'wait', mode='duration', amount=1, unit='days'),
            branches=[('w', 'out', 'a')],
        )
        self.assertFalse(any('loop' in i['message'] for i in check_graph(self.env, 'res.partner', graph)))

    def test_publish_refuses_errors(self):
        workflow = self.make_workflow(chain(node('s', 'start', trigger='create'), node('c', 'condition')),
                                    publish=False)
        with self.assertRaisesRegex(UserError, 'Set the condition'):
            workflow.action_publish()
        self.assertEqual(workflow.state, 'draft')
        self.assertFalse(workflow.version_ids)

    def test_publish_versions_and_triggers(self):
        workflow = self.make_workflow(chain(node('s', 'start', trigger='create'), node('e', 'end')))
        self.assertEqual(workflow.state, 'active')
        self.assertEqual(workflow.version_id.number, 1)
        automation = workflow.automation_id
        self.assertEqual(automation.trigger, 'on_create')
        self.assertEqual(automation.state, 'om_workflow')
        self.assertFalse(workflow.has_changes)

        # publishing the same chart again makes no new version
        workflow.action_publish()
        self.assertEqual(len(workflow.version_ids), 1)

        graph = dict(workflow.graph)
        graph['nodes'] = [*graph['nodes'], node('n', 'note', body='hi')]
        workflow.graph = graph
        self.assertTrue(workflow.has_changes)
        workflow.action_publish()
        self.assertEqual(workflow.version_id.number, 2)
        self.assertFalse(automation.exists(), "the old rule is replaced")
        self.assertTrue(workflow.automation_id)

        workflow.action_pause()
        self.assertFalse(workflow.automation_id)
        self.assertEqual(workflow.state, 'paused')

    def test_model_locked_after_publish(self):
        workflow = self.make_workflow(chain(node('s', 'start', trigger='create'), node('e', 'end')))
        with self.assertRaises(UserError):
            workflow.model_id = self.env['ir.model']._get('res.users')

    def test_change_trigger(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='change', fields=['phone'], domain="[('phone', '!=', False)]"),
            node('n', 'note', body='Phone set'),
        ))
        automation = workflow.automation_id
        self.assertEqual(automation.trigger, 'on_create_or_write')
        self.assertEqual(automation.trigger_field_ids.name, 'phone')
        self.assertTrue(automation.filter_pre_domain)

        partner = self.env['res.partner'].create({'name': 'Quiet'})
        self.assertFalse(self.runs_of(workflow, partner))
        partner.write({'phone': '123'})
        run = self.runs_of(workflow, partner)
        self.assertEqual(run.state, 'done')
        # becomes true only once: another change while true starts nothing
        partner.write({'phone': '456'})
        self.assertEqual(len(self.runs_of(workflow, partner)), 1)

    def test_date_trigger(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='date', date_field='create_date', amount=2, unit='weeks', direction='after'),
            node('e', 'end'),
        ))
        automation = workflow.automation_id
        self.assertEqual(automation.trigger, 'on_time')
        self.assertEqual(automation.trg_date_range, 14)
        self.assertEqual(automation.trg_date_range_type, 'day')

    def test_manual_trigger(self):
        workflow = self.make_workflow(chain(node('s', 'start', trigger='manual'), node('n', 'note', body='Hand')))
        action = workflow.manual_action_id
        self.assertEqual(action.binding_model_id, self.partner_model)
        self.assertFalse(workflow.automation_id)
        partners = self.env['res.partner'].create([{'name': 'A'}, {'name': 'B'}])
        result = action.with_context(active_model='res.partner', active_ids=partners.ids,
                                     active_id=partners[0].id).run()
        self.assertEqual(result['params']['type'], 'success')
        self.assertEqual(len(self.runs_of(workflow)), 2)

    def test_run_bindings(self):
        # workflows already running in the database keep their entry
        self.Workflow.search([('state', '=', 'active')]).action_pause()
        workflow = self.make_workflow(chain(node('s', 'start', trigger='create'), node('e', 'end')))
        Window = self.env['ir.actions.act_window']
        domain = [('res_model', '=', 'om.workflow.run'), ('binding_model_id', '=', self.partner_model.id)]
        self.assertEqual(Window.search_count(domain), 1)
        other = self.make_workflow(chain(node('s', 'start', trigger='create'), node('e', 'end')))
        self.assertEqual(Window.search_count(domain), 1, "one entry per model")
        workflow.action_pause()
        self.assertEqual(Window.search_count(domain), 1)
        other.unlink()
        self.assertEqual(Window.search_count(domain), 0)

    def test_designer_round_trip(self):
        workflow = self.make_workflow(chain(node('s', 'start', trigger='create'), node('e', 'end')), publish=False)
        data = workflow.designer_load()
        self.assertEqual(data['workflow']['model'], 'res.partner')
        self.assertTrue(any(f['name'] == 'email' for f in data['fields']))
        self.assertFalse(any(f['name'].startswith('message_') for f in data['fields']))
        graph = data['graph']
        graph['nodes'].append(node('c', 'condition'))
        result = workflow.designer_save(graph, 'Renamed')
        self.assertEqual(workflow.name, 'Renamed')
        self.assertTrue(any(i['node'] == 'c' for i in result['issues']))

    def test_only_admin_designs(self):
        with self.assertRaises(AccessError):
            self.Workflow.with_user(self.supervisor).create({'name': 'No', 'model_id': self.partner_model.id})
        workflow = self.make_workflow(chain(node('s', 'start', trigger='create'), node('e', 'end')), publish=False)
        with self.assertRaises(AccessError):
            workflow.with_user(self.supervisor).action_publish()
        self.assertTrue(workflow.with_user(self.supervisor).name)

    def test_uninstall_cleanup(self):
        workflow = self.make_workflow(chain(node('s', 'start', trigger='create'), node('e', 'end')))
        automation = workflow.automation_id
        from odoo.addons.om_automation_studio import uninstall_hook  # noqa: PLC0415
        uninstall_hook(self.env.cr, self.env.registry)
        self.assertFalse(automation.exists())
        self.assertFalse(self.env['ir.actions.act_window'].search_count(
            [('res_model', '=', 'om.workflow.run'), ('binding_model_id', '!=', False)]))
