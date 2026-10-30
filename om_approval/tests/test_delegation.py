from datetime import timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from .test_button_rule import ApprovalCase


@tagged('post_install', '-at_install')
class TestDelegation(ApprovalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.substitute = new_test_user(cls.env, 'om_substitute', groups='base.group_user,base.group_partner_manager')
        cls.second = new_test_user(cls.env, 'om_second_substitute', groups='base.group_user')
        cls.today = fields.Date.today()

    def delegate(self, user, delegate, days=(0, 5), flows=None, by=None):
        return self.env['approval.delegation'].with_user(by or user).create({
            'user_id': user.id, 'delegate_id': delegate.id,
            'date_from': self.today + timedelta(days=days[0]), 'date_to': self.today + timedelta(days=days[1]),
            'flow_ids': [Command.set(flows.ids)] if flows else []})

    def pending_line(self):
        self.gate(self.requester)
        request = self.request_of()
        return request, request.line_ids.filtered(lambda line: line.state == 'pending')

    def test_substitute_of_a_waiting_step(self):
        request, line = self.pending_line()
        self.assertEqual(line.approver_user_ids, self.approver)
        self.delegate(self.approver, self.substitute)
        self.assertEqual(line.approver_user_ids, self.approver | self.substitute)
        self.assertIn(self.substitute, request.activity_ids.user_id, 'the substitute gets the activity')
        self.assertIn(self.substitute.partner_id, request.message_ids.partner_ids)
        request.with_user(self.substitute).action_approve()
        self.assertEqual(line.state, 'approved')
        self.assertEqual(line.note, 'On behalf of %s.' % self.approver.name)

    def test_substitute_of_a_step_becoming_due(self):
        self.delegate(self.approver, self.substitute)
        _request, line = self.pending_line()
        self.assertIn(self.substitute, line.approver_user_ids)
        self.assertEqual(line.substitutes, {str(self.substitute.id): [self.approver.name]})

    def test_approver_still_decides(self):
        self.delegate(self.approver, self.substitute)
        request, line = self.pending_line()
        request.with_user(self.approver).action_approve()
        self.assertEqual((line.state, line.note), ('approved', False))

    def test_period_and_flows(self):
        self.delegate(self.approver, self.substitute, days=(2, 4))
        other_button = self.env['approval.button'].create({
            'model_id': self.env['ir.model']._get_id('res.partner'), 'method': 'action_unarchive', 'name': 'Restore'})
        other_flow = self.env['approval.rule'].create({
            'name': 'Other', 'model_id': self.env['ir.model']._get_id('res.partner'), 'button_id': other_button.id})
        self.delegate(self.approver, self.second, flows=other_flow)
        _request, line = self.pending_line()
        self.assertEqual(line.approver_user_ids, self.approver, 'not yet away, and not for this flow')
        with freeze_time(self.today + timedelta(days=2)):
            self.env['approval.line']._cron_follow_up()
        self.assertEqual(line.approver_user_ids, self.approver | self.substitute)

    def test_chain_and_loop(self):
        self.delegate(self.approver, self.substitute)
        self.delegate(self.substitute, self.second)
        self.delegate(self.second, self.approver)
        _request, line = self.pending_line()
        self.assertEqual(line.approver_user_ids, self.approver | self.substitute | self.second)
        self.assertEqual(line.substitutes[str(self.second.id)], [self.substitute.name])

    def test_requester_is_not_a_substitute(self):
        self.flow.self_approve = False
        self.delegate(self.approver, self.requester)
        _request, line = self.pending_line()
        self.assertEqual(line.approver_user_ids, self.approver, 'the requester does not approve their request')

    def test_rights(self):
        with self.assertRaises((AccessError, ValidationError)):
            self.delegate(self.director, self.substitute, by=self.approver)
        with self.assertRaises(ValidationError):
            self.delegate(self.approver, self.approver)
        with self.assertRaises(ValidationError):
            self.delegate(self.approver, self.substitute, days=(3, 1))
        manager = new_test_user(self.env, 'om_approval_admin',
                                groups='base.group_user,om_approval.group_approval_manager')
        self.assertTrue(self.delegate(self.director, self.substitute, by=manager))
        mine = self.delegate(self.approver, self.substitute)
        self.assertEqual(mine.with_user(self.substitute).state, 'active', 'the substitute reads it')
        with self.assertRaises((AccessError, ValidationError)):
            mine.with_user(self.substitute).write({'note': 'mine now'})

    def test_remind_then_escalate(self):
        self.flow.step_ids.write({'remind_days': 1, 'escalate_days': 3, 'escalate_type': 'user',
                                  'escalate_user_ids': [Command.set(self.director.ids)]})
        request, line = self.pending_line()
        Line = self.env['approval.line']
        start = fields.Datetime.now()
        with freeze_time(start + timedelta(hours=12)):
            Line._cron_follow_up()
        self.assertFalse(line.date_reminded)
        with freeze_time(start + timedelta(days=1, hours=1)):
            Line._cron_follow_up()
        self.assertTrue(line.date_reminded)
        self.assertEqual(line.approver_user_ids, self.approver)
        with freeze_time(start + timedelta(days=3, hours=1)):
            Line._cron_follow_up()
        self.assertEqual(line.approver_user_ids, self.approver | self.director)
        self.assertTrue(line.date_escalated)
        request.with_user(self.director).action_approve()
        self.assertEqual(line.state, 'approved')

    def test_escalate_to_the_fallback(self):
        self.flow.step_ids.write({'escalate_days': 1, 'escalate_type': 'group',
                                  'escalate_group_id': self.env['res.groups'].create({'name': 'Nobody'}).id})
        admin = new_test_user(self.env, 'om_fallback_admin',
                              groups='base.group_user,om_approval.group_approval_manager')
        _request, line = self.pending_line()
        with freeze_time(fields.Datetime.now() + timedelta(days=1, hours=1)):
            self.env['approval.line']._cron_follow_up()
        self.assertIn(admin, line.approver_user_ids, 'nobody in the group: the fallback approvers are asked')
