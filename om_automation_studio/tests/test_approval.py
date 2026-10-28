from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from .common import WorkflowCase, chain, node


@tagged('post_install', '-at_install')
class TestApproval(WorkflowCase):

    def approval_workflow(self, **config):
        return self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('a', 'approval', assign='user', user_id=self.approver.id,
                 title='Approve {{ object.name }}', **config),
            node('yes', 'update', values=[{'field': 'comment', 'mode': 'value', 'value': 'Approved'}]),
            node('end', 'end'),
            node('no', 'update', values=[{'field': 'comment', 'mode': 'value', 'value': 'Rejected'}]),
            branches=[('a', 'rejected', 'no')],
        ))

    def test_approve(self):
        workflow = self.approval_workflow()
        partner = self.env['res.partner'].create({'name': 'Deal'})
        workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        self.assertEqual(run.state, 'waiting')
        approval = run.approval_ids
        self.assertEqual(approval.name, 'Approve Deal')
        self.assertEqual(approval.activity_ids.user_id, self.approver)

        approval.with_user(self.approver).write({'comment': 'Fine by me'})
        approval.with_user(self.approver).action_approve()
        self.assertEqual(approval.state, 'approved')
        self.assertEqual(approval.decided_by_id, self.approver)
        self.assertFalse(approval.activity_ids)
        self.assertEqual(run.state, 'done')
        self.assertEqual(self.path(run)[1], ('a', 'approved'))
        self.assertEqual([key for key, __ in self.path(run)], ['s', 'a', 'yes', 'end'])
        self.assertIn('Approved', partner.comment)

    def test_reject(self):
        workflow = self.approval_workflow()
        partner = self.env['res.partner'].create({'name': 'Bad Deal'})
        workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        run.approval_ids.with_user(self.approver).action_reject()
        self.assertEqual(self.path(run)[1], ('a', 'rejected'))
        self.assertEqual([key for key, __ in self.path(run)], ['s', 'a', 'no'])
        self.assertIn('Rejected', partner.comment)
        self.assertTrue(partner.message_ids.filtered(lambda m: 'Rejected by' in (m.body or '')))

    def test_only_the_approver_answers(self):
        workflow = self.approval_workflow()
        partner = self.env['res.partner'].create({'name': 'Private'})
        workflow._start_runs(partner)
        approval = self.runs_of(workflow, partner).approval_ids
        with self.assertRaises(AccessError):
            approval.with_user(self.other_user).read(['name'])
        with self.assertRaises(UserError):
            approval.with_user(self.supervisor).action_approve()
        with self.assertRaises(AccessError):
            approval.with_user(self.approver).write({'state': 'approved'})
        self.assertEqual(approval.state, 'pending')

    def test_admin_answers_on_behalf(self):
        workflow = self.approval_workflow()
        partner = self.env['res.partner'].create({'name': 'Away'})
        workflow._start_runs(partner)
        approval = self.runs_of(workflow, partner).approval_ids
        admin = new_test_user(self.env, 'om_wd_admin', groups='base.group_system')
        approval.with_user(admin).action_approve()
        self.assertEqual(approval.state, 'approved')
        self.assertEqual(approval.decided_by_id, admin)
        self.assertIn(f"on behalf of {self.approver.name}", partner.message_ids[0].body)
        told = approval.message_ids.filtered(lambda message: self.approver.partner_id in message.partner_ids)
        self.assertTrue(told, "the approver is told that someone answered for them")

    def test_approver_only(self):
        workflow = self.approval_workflow(approver_only=True)
        partner = self.env['res.partner'].create({'name': 'Strict'})
        workflow._start_runs(partner)
        approval = self.runs_of(workflow, partner).approval_ids
        admin = new_test_user(self.env, 'om_wd_admin', groups='base.group_system')
        self.assertFalse(approval.with_user(admin).can_decide)
        with self.assertRaises(UserError):
            approval.with_user(admin).action_approve()
        approval.with_user(self.approver).action_approve()
        self.assertEqual(approval.state, 'approved')
        self.assertNotIn("on behalf", partner.message_ids[0].body)

    def test_approver_from_field(self):
        workflow = self.make_workflow(chain(
            node('s', 'start', trigger='manual'),
            node('a', 'approval', assign='field', user_field='user_id'),
        ))
        partner = self.env['res.partner'].create({'name': 'Owned', 'user_id': self.approver.id})
        workflow._start_runs(partner)
        self.assertEqual(self.runs_of(workflow, partner).approval_ids.user_id, self.approver)

        orphan = self.env['res.partner'].create({'name': 'Orphan'})
        with mute_logger('odoo.addons.om_automation_studio.models.om_workflow_run'):
            workflow._start_runs(orphan)
        self.assertEqual(self.runs_of(workflow, orphan).state, 'failed')

    def test_timeout(self):
        workflow = self.approval_workflow(timeout=True, amount=1, unit='days')
        partner = self.env['res.partner'].create({'name': 'Slow Answer'})
        with freeze_time('2026-02-01 09:00:00'):
            workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        approval = run.approval_ids
        self.assertEqual(approval.deadline, fields.Datetime.to_datetime('2026-02-02 09:00:00'))
        with freeze_time('2026-02-02 09:30:00'):
            now = fields.Datetime.now()
            self.Run._due_runs(now)._wake(now)
        self.assertEqual(approval.state, 'expired')
        self.assertEqual(run.state, 'done', "no arrow on the time limit exit: the run ends")
        self.assertEqual(self.path(run)[1], ('a', 'timeout'))

    def test_cancelled_run_closes_approval(self):
        workflow = self.approval_workflow()
        partner = self.env['res.partner'].create({'name': 'Withdrawn'})
        workflow._start_runs(partner)
        run = self.runs_of(workflow, partner)
        run.with_user(self.supervisor).action_cancel()
        self.assertEqual(run.approval_ids.state, 'cancelled')
        self.assertFalse(run.approval_ids.activity_ids)

    def test_approval_wake_skips_before_deadline(self):
        workflow = self.approval_workflow(timeout=True, amount=3, unit='days')
        partner = self.env['res.partner'].create({'name': 'Patient Approver'})
        workflow._start_runs(partner)
        now = fields.Datetime.now() + timedelta(days=1)
        self.Run._due_runs(now)._wake(now)
        self.assertEqual(self.runs_of(workflow, partner).state, 'waiting')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor_user = new_test_user(cls.env, 'om_wd_editor', groups='base.group_user,base.group_partner_manager')

    def editor(self, partner):
        """ ``partner`` as a salesperson who may change contacts. """
        return partner.with_user(self.editor_user)

    def lock_workflow(self, **config):
        return self.make_workflow(chain(
            node('s', 'start', trigger='manual', stop_domain="[('ref', '=', 'withdrawn')]"),
            node('a', 'approval', assign='user', user_id=self.approver.id, title='Approve {{ object.name }}',
                 **config),
            node('n', 'note', body='Answered'),
        ))

    def test_lock_blocks_the_fields(self):
        workflow = self.lock_workflow(lock=True, lock_fields=['comment'])
        partner = self.env['res.partner'].create({'name': 'Locked'})
        workflow._start_runs(partner)
        with self.assertRaisesRegex(UserError, 'waits for approval by') as error:
            self.editor(partner).write({'comment': 'Too early'})
        self.assertIn(': Notes cannot change', str(error.exception), "the field by its label, not as a list")
        self.editor(partner).write({'phone': '123'})
        self.assertEqual(partner.phone, '123', "the other fields stay free")
        # the workflow itself and the system are not blocked
        partner.sudo().write({'comment': 'By the system'})

        self.runs_of(workflow, partner).approval_ids.with_user(self.approver).action_approve()
        self.editor(partner).write({'comment': 'Now fine'})
        self.assertIn('Now fine', partner.comment)

    def test_lock_any_change(self):
        workflow = self.lock_workflow(lock=True, lock_mode='all')
        partner = self.env['res.partner'].create({'name': 'Frozen'})
        workflow._start_runs(partner)
        with self.assertRaises(UserError):
            self.editor(partner).write({'phone': '123'})

    def test_no_lock(self):
        workflow = self.lock_workflow(lock=False)
        partner = self.env['res.partner'].create({'name': 'Free'})
        workflow._start_runs(partner)
        self.editor(partner).write({'comment': 'Free to change', 'phone': '1'})
        self.assertNotIn('res.partner', self.env['om.workflow.approval']._locked_models())

    def test_stop_condition_releases_the_lock(self):
        workflow = self.lock_workflow(lock=True, lock_fields=['comment'])
        partner = self.env['res.partner'].create({'name': 'Withdrawn'})
        workflow._start_runs(partner)
        self.editor(partner).write({'ref': 'withdrawn'})
        self.editor(partner).write({'comment': 'No approval needed any more'})
        run = self.runs_of(workflow, partner)
        self.assertEqual(run.state, 'done')
        self.assertEqual(run.approval_ids.state, 'cancelled')

    def test_record_shows_the_approval(self):
        workflow = self.lock_workflow(lock=True, lock_fields=['comment'])
        partner = self.env['res.partner'].create({'name': 'Shown'})
        workflow._start_runs(partner)
        approval = self.runs_of(workflow, partner).approval_ids
        note = partner.message_ids.filtered(lambda m: 'Waiting for approval by' in (m.body or ''))
        self.assertTrue(note)
        self.assertIn(f'data-oe-id="{approval.id}"', note.body)

        Approval = self.env['om.workflow.approval']
        self.assertIn('res.partner', Approval.get_approval_models())
        # a user who cannot read the approval still sees it on the record
        pending = Approval.with_user(self.other_user).get_pending('res.partner', partner.id)
        self.assertEqual(pending[0]['user'], self.approver.name)
        self.assertFalse(pending[0]['can_decide'])
        self.assertEqual(pending[0]['locked'], ['Notes'])
        self.assertTrue(Approval.with_user(self.approver).get_pending('res.partner', partner.id)[0]['can_decide'])
        approval.with_user(self.approver).action_reject()
        self.assertFalse(Approval.get_pending('res.partner', partner.id))
