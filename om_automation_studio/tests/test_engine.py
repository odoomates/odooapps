from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import WorkflowCase, chain, node


@tagged('post_install', '-at_install')
class TestEngine(WorkflowCase):

    def wake(self, when):
        with freeze_time(when):
            now = fields.Datetime.now()
            self.Run._due_runs(now)._wake(now)

    def test_condition_and_actions(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='create'),
            node('c', 'condition', domain="[('email', '!=', False)]"),
            node('u', 'update', values=[
                {'field': 'comment', 'mode': 'value', 'value': 'Company'},
                {'field': 'ref', 'mode': 'field', 'source': 'name'},
            ]),
            node('n', 'note', body='Hello {{ object.name }}'),
            branches=[('c', 'no', 'n')],
        ))
        company = self.env['res.partner'].create({'name': 'Acme', 'email': 'acme@example.com'})
        person = self.env['res.partner'].create({'name': 'Bob'})

        run = self.runs_of(workflow, company)
        self.assertEqual(run.state, 'done')
        self.assertEqual(self.path(run), [('s', 'out'), ('c', 'yes'), ('u', 'out'), ('n', 'out')])
        self.assertEqual(company.ref, 'Acme')
        self.assertIn('Company', company.comment)
        self.assertIn('Hello Acme', company.message_ids[0].body)

        run = self.runs_of(workflow, person)
        self.assertEqual(self.path(run), [('s', 'out'), ('c', 'no'), ('n', 'out')])
        self.assertFalse(person.ref)

    def test_trigger_domain_and_policy(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='create', domain="[('email', '!=', False)]", policy='single'),
            node('w', 'wait', mode='duration', amount=1, unit='days'),
        ))
        person = self.env['res.partner'].create({'name': 'Bob'})
        self.assertFalse(self.runs_of(workflow, person))
        company = self.env['res.partner'].create({'name': 'Acme', 'email': 'acme@example.com'})
        self.assertEqual(self.runs_of(workflow, company).state, 'waiting')
        # a run is waiting: no second one on the same record
        workflow._start_runs(company)
        self.assertEqual(len(self.runs_of(workflow, company)), 1)

    def test_wait_then_continue(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='create'),
            node('w', 'wait', mode='duration', amount=3, unit='days'),
            node('u', 'update', values=[{'field': 'comment', 'mode': 'value', 'value': 'Later'}]),
        ))
        with freeze_time('2026-01-01 10:00:00'):
            partner = self.env['res.partner'].create({'name': 'Patient'})
        run = self.runs_of(workflow, partner)
        self.assertEqual(run.state, 'waiting')
        self.assertEqual(run.wake_at, fields.Datetime.to_datetime('2026-01-04 10:00:00'))

        self.wake('2026-01-03 10:00:00')
        self.assertEqual(run.state, 'waiting')
        self.wake('2026-01-04 10:01:00')
        self.assertEqual(run.state, 'done')
        self.assertIn('Later', partner.comment)

    def test_wait_for_date(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('w', 'wait', mode='date', date_field='create_date', amount=10, unit='days', direction='after'),
            node('e', 'end'),
        ))
        partner = self.env['res.partner'].create({'name': 'Dated'})
        workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        self.assertEqual(run.wake_at, partner.create_date + timedelta(days=10))

        # a date already past goes on at once
        graph = workflow.graph
        graph['nodes'][1]['config']['direction'] = 'before'
        workflow.graph = graph
        workflow.action_publish()
        other = self.env['res.partner'].create({'name': 'Late'})
        workflow._start_runs(other)
        self.assertEqual(self.runs_of(workflow, other).state, 'done')

    def test_wait_until_and_timeout(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('w', 'wait_until', domain="[('email', '!=', False)]", timeout=True, amount=2, unit='days'),
            node('ok', 'note', body='Got it'),
            node('e', 'end'),
            branches=[('w', 'timeout', 'e')],
        ))
        fast, slow = self.env['res.partner'].create([{'name': 'Fast'}, {'name': 'Slow'}])
        with freeze_time('2026-05-01 08:00:00'):
            workflow._start_runs(fast | slow)
        fast.email = 'fast@example.com'
        self.wake('2026-05-01 08:05:00')
        self.assertEqual(self.path(self.runs_of(workflow, fast))[1], ('w', 'done'))
        self.assertEqual(self.runs_of(workflow, slow).state, 'waiting')
        self.wake('2026-05-03 08:01:00')
        run = self.runs_of(workflow, slow)
        self.assertEqual(run.state, 'done')
        self.assertEqual(self.path(run)[1], ('w', 'timeout'))

    def test_stop_condition(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual', stop_domain="[('active', '=', False)]"),
            node('w', 'wait', mode='duration', amount=1, unit='days'),
            node('n', 'note', body='Should not be posted'),
        ))
        partner = self.env['res.partner'].create({'name': 'Leaving'})
        workflow._start_runs(partner)
        partner.active = False
        self.wake(fields.Datetime.now() + timedelta(days=2))
        run = self.runs_of(workflow, partner)
        self.assertEqual(run.state, 'done')
        self.assertNotIn('n', [step.node_key for step in run.step_ids])

    def test_failing_step_rolls_back_and_retries(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('u', 'update', values=[{'field': 'comment', 'mode': 'value', 'value': 'Before'}]),
            node('a', 'activity', activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                 summary='Call', assign='field', user_field='user_id'),
        ))
        partner = self.env['res.partner'].create({'name': 'No Salesperson'})
        with mute_logger('odoo.addons.om_automation_studio.models.om_workflow_run'):
            workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        # no user on the field: the activity goes to the current user
        self.assertEqual(run.state, 'done')

        # a step that raises fails the run, without undoing the record write that started it
        workflow2 = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            # the tag has no name, which the database refuses
            node('c', 'create', model='res.partner.category', values=[
                {'field': 'color', 'mode': 'value', 'value': 3}]),
        ))
        partner2 = self.env['res.partner'].create({'name': 'Tagless'})
        with mute_logger('odoo.addons.om_automation_studio.models.om_workflow_run', 'odoo.sql_db'):
            workflow2._start_runs(partner2)
        run = self.runs_of(workflow2, partner2)
        self.assertEqual(run.state, 'failed')
        self.assertTrue(run.error)
        self.assertEqual(run.step_ids[-1].state, 'failed')

        # fix the version graph (as a new publish would not change this run) and retry
        graph = run.version_id.graph
        graph['nodes'][1]['config']['values'] = [{'field': 'name', 'mode': 'value', 'value': 'From workflow'}]
        run.version_id.sudo().write({'graph': graph})
        run.with_user(self.supervisor).action_retry()
        self.assertEqual(run.state, 'done')
        self.assertTrue(self.env['res.partner.category'].search([('name', '=', 'From workflow')]))

    def test_create_with_link(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('c', 'create', model='res.partner', link_field='parent_id', values=[
                {'field': 'name', 'mode': 'value', 'value': 'Contact person'},
                {'field': 'email', 'mode': 'field', 'source': 'email'},
            ]),
        ))
        company = self.env['res.partner'].create({'name': 'Parent', 'is_company': True, 'email': 'p@example.com'})
        workflow._start_runs(company)
        child = company.child_ids
        self.assertEqual(child.name, 'Contact person')
        self.assertEqual(child.email, 'p@example.com')

    def test_runs_keep_their_version(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('w', 'wait', mode='duration', amount=1, unit='days'),
            node('u', 'update', values=[{'field': 'comment', 'mode': 'value', 'value': 'v1'}]),
        ))
        partner = self.env['res.partner'].create({'name': 'Old Run'})
        workflow._start_runs(partner)
        graph = workflow.graph
        graph['nodes'][2]['config']['values'][0]['value'] = 'v2'
        workflow.graph = graph
        workflow.action_publish()
        self.assertEqual(workflow.version_id.number, 2)

        self.wake(fields.Datetime.now() + timedelta(days=2))
        run = self.runs_of(workflow, partner)
        self.assertEqual(run.version, 1)
        self.assertIn('v1', partner.comment)

    def test_paused_runs_wait(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('w', 'wait', mode='duration', amount=1, unit='hours'),
            node('e', 'end'),
        ))
        partner = self.env['res.partner'].create({'name': 'Paused'})
        workflow._start_runs(partner)
        workflow.action_pause()
        self.wake(fields.Datetime.now() + timedelta(hours=2))
        self.assertEqual(self.runs_of(workflow, partner).state, 'waiting')
        workflow.action_publish()
        self.wake(fields.Datetime.now() + timedelta(hours=2))
        self.assertEqual(self.runs_of(workflow, partner).state, 'done')

    def test_deleted_record_fails_run(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('w', 'wait', mode='duration', amount=1, unit='hours'),
            node('e', 'end'),
        ))
        partner = self.env['res.partner'].create({'name': 'Gone'})
        workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        partner.unlink()
        self.wake(fields.Datetime.now() + timedelta(hours=2))
        self.assertEqual(run.state, 'failed')

    def test_cancel_by_supervisor(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('w', 'wait', mode='duration', amount=1, unit='hours'),
        ))
        partner = self.env['res.partner'].create({'name': 'Cancelled'})
        workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        run.with_user(self.supervisor).action_cancel()
        self.assertEqual(run.state, 'cancelled')
        self.assertEqual(run.step_ids[-1].state, 'cancelled')

    def test_email_step(self):
        template = self.env['mail.template'].create({
            'name': 'Hello',
            'model_id': self.partner_model.id,
            'subject': 'Hello {{ object.name }}',
            'body_html': '<p>Welcome</p>',
            'email_to': '{{ object.email }}',
        })
        workflow = self.make_workflow(chain(node('s', 'start', trigger='manual'), node('m', 'email',
                                                                                    template_id=template.id)))
        partner = self.env['res.partner'].create({'name': 'Mailed', 'email': 'm@example.com'})
        workflow._start_runs(partner)
        self.assertEqual(self.runs_of(workflow, partner).state, 'done')
        self.assertTrue(partner.message_ids.filtered(lambda m: 'Welcome' in (m.body or '')))
