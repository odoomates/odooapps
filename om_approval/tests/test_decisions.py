from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .test_button_rule import ApprovalCase


@tagged('post_install', '-at_install')
class TestNotes(ApprovalCase):

    def tearDown(self):
        self.env['approval.request']._restore_lock()
        super().tearDown()

    def test_approver_notes(self):
        self.flow.write({'approve_note': 'required', 'refuse_note': 'optional'})
        self.gate(self.requester)
        request = self.request_of()
        with self.assertRaises(UserError):
            request.with_user(self.approver).action_approve()
        action = request.with_user(self.approver).action_open_approve()
        self.assertEqual((action['res_model'], action['context']['default_decision']), ('approval.decide', 'approve'))
        wizard = self.env['approval.decide'].with_user(self.approver).create(
            {'request_id': request.id, 'decision': 'approve', 'note': 'Good customer'})
        self.assertEqual(wizard.note_mode, 'required')
        wizard.action_confirm()
        self.assertEqual(request.state, 'done')
        self.assertIn('Good customer', request.line_ids.note)

    def test_approve_at_once_without_note(self):
        self.flow.approve_note = 'none'
        self.gate(self.requester)
        request = self.request_of()
        self.assertTrue(request.with_user(self.approver).action_open_approve() is True)
        self.assertEqual(request.state, 'done')

    def test_refuse_without_note_when_optional(self):
        self.gate(self.requester)
        request = self.request_of()
        with self.assertRaises(UserError):
            request.with_user(self.approver).action_refuse()
        self.flow.refuse_note = 'optional'
        request.with_user(self.approver).action_refuse()
        self.assertEqual(request.state, 'refused')

    def test_requester_note_and_files(self):
        self.flow.request_note = 'required'
        action = self.gate(self.requester)
        self.assertEqual(action['res_model'], 'approval.ask')
        self.assertFalse(self.request_of(), 'nothing is asked before the note')
        context = {key.removeprefix('default_'): value for key, value in action['context'].items()}
        Ask = self.env['approval.ask'].with_user(self.requester)
        with self.assertRaises(UserError):
            Ask.create(dict(context, note='')).action_ask()
        attachment = self.env['ir.attachment'].with_user(self.requester).create({
            'name': 'quote.txt', 'raw': b'quote', 'res_model': 'approval.ask', 'res_id': 0})
        result = Ask.create(dict(context, note='Customer moves abroad',
                                 attachment_ids=[Command.set(attachment.ids)])).action_ask()
        self.assertEqual(result['tag'], 'display_notification')
        request = self.request_of()
        self.assertEqual((request.state, request.request_note), ('to_approve', 'Customer moves abroad'))
        self.assertEqual(request.attachment_ids, attachment)
        self.assertEqual((attachment.res_model, attachment.res_id), ('approval.request', request.id))
        info = self.env['approval.request'].with_user(self.approver).get_record_approvals('res.partner',
                                                                                          self.partner.id)
        self.assertEqual(info['requests'][0]['request_note'], 'Customer moves abroad')
        self.assertEqual(info['requests'][0]['attachments'][0]['name'], 'quote.txt')

    def test_note_asked_then_approved_at_once_runs_the_button(self):
        self.flow.request_note = 'optional'
        action = self.gate(self.approver)
        context = {key.removeprefix('default_'): value for key, value in action['context'].items()}
        self.env['approval.ask'].with_user(self.approver).create(dict(context, note='Mine')).action_ask()
        self.assertEqual(self.request_of().state, 'done')
        self.assertFalse(self.partner.active)

    def test_api_cannot_give_a_required_note(self):
        self.flow.request_note = 'required'
        with self.assertRaises(UserError):
            self.env['approval.request'].with_user(self.requester)._gate_call(
                'res.partner', 'action_archive', [self.partner.ids], api=True)
        self.flow.request_note = 'optional'
        action = self.env['approval.request'].with_user(self.requester)._gate_call(
            'res.partner', 'action_archive', [self.partner.ids], api=True)
        self.assertEqual(action['tag'], 'display_notification', 'an optional note is left empty')
        self.assertEqual(self.request_of().state, 'to_approve')

    def test_approved_records_wait_for_the_others(self):
        """ Clicked for two records, one approved: nothing runs, and the approval is kept for the next click. """
        other = self.env['res.partner'].create({'name': 'Other Customer'})
        self.gate(self.requester)
        approved = self.request_of()
        approved.with_user(self.approver).action_approve()  # ran the button
        self.partner.action_unarchive()
        self.flow.run_on_approval = False
        self.gate(self.requester)
        approved = self.request_of()
        approved.with_user(self.approver).action_approve()
        self.assertEqual(approved.state, 'approved')
        action = self.env['approval.request'].with_user(self.requester)._gate_button(
            'res.partner', 'action_archive', (self.partner | other).ids)
        self.assertTrue(action, 'the other record asks its approval')
        self.assertEqual(approved.state, 'approved', 'the approval is not used up while the other waits')


@tagged('post_install', '-at_install')
class TestAmountAndModes(ApprovalCase):

    def test_amount(self):
        self.flow.write({'amount_field': 'color', 'amount_min': 5})
        small = self.env['res.partner'].create({'name': 'Small', 'color': 3})
        big = self.env['res.partner'].create({'name': 'Big', 'color': 8})
        self.assertIsNone(self.gate(self.requester, small))
        self.assertTrue(self.gate(self.requester, big))
        self.assertIn('Color Index above', str(self.flow.summary))

    def test_step_above_an_amount(self):
        self.flow.write({'amount_field': 'color', 'amount_min': 0, 'step_ids': [Command.create({
            'name': 'Director', 'sequence': 20, 'approver_type': 'user', 'user_ids': [Command.link(self.director.id)],
            'amount_min': 5})]})
        low = self.env['res.partner'].create({'name': 'Low', 'color': 2})
        self.gate(self.requester, low)
        self.assertEqual(self.request_of(low).line_ids.mapped('name'), ['Approvers'])
        high = self.env['res.partner'].create({'name': 'High', 'color': 9})
        self.gate(self.requester, high)
        self.assertEqual(self.request_of(high).line_ids.mapped('name'), ['Approvers', 'Director'])

    def test_all_of_them(self):
        self.approvers.user_ids = [Command.link(self.director.id)]
        self.flow.step_ids.approval_mode = 'all'
        self.gate(self.requester)
        request = self.request_of()
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, 'to_approve')
        self.assertEqual(request.line_ids.progress, '1 / 2')
        self.assertFalse(request.with_user(self.approver).can_approve, 'approved once')
        self.assertTrue(request.with_user(self.director).can_approve)
        request.with_user(self.director).action_approve()
        self.assertEqual(request.state, 'done')
        self.assertFalse(self.partner.active)

    def test_a_number_of_them_and_a_refusal(self):
        third = new_test_user(self.env, 'om_third', groups='base.group_user')
        self.approvers.user_ids = [Command.link(self.director.id), Command.link(third.id)]
        self.flow.step_ids.write({'approval_mode': 'count', 'approval_count': 2})
        self.gate(self.requester)
        request = self.request_of()
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.line_ids.progress, '1 / 2')
        request.with_user(third).action_refuse('No')
        self.assertEqual(request.state, 'refused', 'a refusal refuses the step')

    def test_manager_decides_for_the_step(self):
        manager = new_test_user(self.env, 'om_modes_manager',
                                groups='base.group_user,om_approval.group_approval_manager')
        self.approvers.user_ids = [Command.link(self.director.id)]
        self.flow.step_ids.approval_mode = 'all'
        self.gate(self.requester)
        self.request_of().with_user(manager).action_approve()
        self.assertEqual(self.request_of().state, 'done')

    def test_requester_counts_as_one(self):
        self.approvers.user_ids = [Command.link(self.requester.id), Command.link(self.director.id)]
        self.flow.step_ids.write({'approval_mode': 'count', 'approval_count': 2})
        self.gate(self.requester)
        line = self.request_of().line_ids
        self.assertEqual(line.approved_user_ids, self.requester)
        self.assertEqual(line.progress, '1 / 2')


@tagged('post_install', '-at_install')
class TestRefusalBanner(ApprovalCase):

    def test_refusal_shows_until_dismissed(self):
        self.gate(self.requester)
        request = self.request_of()
        request.with_user(self.approver).action_refuse('Open invoices')
        Request = self.env['approval.request'].with_user(self.requester)
        [item] = Request.get_record_approvals('res.partner', self.partner.id)['requests']
        self.assertEqual((item['state'], item['refused_reason'], item['refused_by']),
                         ('refused', 'Open invoices', self.approver.name))
        self.assertTrue(item['can_dismiss'])
        self.assertFalse(Request.get_record_approvals('res.partner', self.partner.id)['locked'])
        with self.assertRaises(UserError):
            request.with_user(self.director).action_dismiss_refusal()
        request.with_user(self.requester).action_dismiss_refusal()
        self.assertFalse(Request.get_record_approvals('res.partner', self.partner.id)['requests'])

    def test_refusal_hidden_once_asked_again(self):
        self.gate(self.requester)
        self.request_of().with_user(self.approver).action_refuse('No')
        self.gate(self.requester)
        items = self.env['approval.request'].with_user(self.requester).get_record_approvals(
            'res.partner', self.partner.id)['requests']
        self.assertEqual([item['state'] for item in items], ['to_approve'])
