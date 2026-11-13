import json

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


class ApprovalCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(cls.env, 'om_requester', groups='base.group_user,base.group_partner_manager')
        cls.approver = new_test_user(cls.env, 'om_approver', groups='base.group_user,base.group_partner_manager')
        cls.director = new_test_user(cls.env, 'om_director', groups='base.group_user,base.group_partner_manager')
        cls.approvers = cls.env['res.groups'].create({'name': 'Partner Approvers', 'user_ids': [
            Command.link(cls.approver.id)]})
        cls.button = cls.env['approval.button'].create({
            'model_id': cls.env['ir.model']._get_id('res.partner'), 'method': 'action_archive', 'name': 'Archive'})
        cls.flow = cls.env['approval.rule'].create({
            'name': 'Archive a partner',
            'model_id': cls.env['ir.model']._get_id('res.partner'),
            'button_id': cls.button.id,
            'request_note': 'none',
            'step_ids': [Command.create({'name': 'Approvers', 'approver_type': 'group',
                                         'group_id': cls.approvers.id})],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Big Customer'})

    def gate(self, user, partner=None):
        Request = self.env['approval.request'].with_user(user)
        return Request._gate_button('res.partner', 'action_archive', (partner or self.partner).ids)

    def request_of(self, partner=None):
        return self.env['approval.request'].search([
            ('res_model', '=', 'res.partner'), ('res_id', '=', (partner or self.partner).id)], order='id desc', limit=1)


@tagged('post_install', '-at_install')
class TestButtonRule(ApprovalCase):

    def test_click_asks_then_runs_once_approved(self):
        action = self.gate(self.requester)
        self.assertEqual(action['tag'], 'display_notification')
        request = self.request_of()
        self.assertEqual(request.state, 'to_approve')
        self.assertEqual(request.requester_id, self.requester)
        self.assertEqual(request.approver_user_ids, self.approver)
        self.assertTrue(self.partner.active)
        self.assertEqual(request.activity_ids.user_id, self.approver)

        # clicking again does not ask twice
        self.assertTrue(self.gate(self.requester))
        self.assertEqual(self.request_of(), request)

        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, 'done', 'the button ran as the requester')
        self.assertFalse(self.partner.active)
        self.assertFalse(request.activity_ids)

    def test_click_again_when_not_run_on_approval(self):
        self.flow.run_on_approval = False
        self.gate(self.requester)
        request = self.request_of()
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertTrue(self.partner.active)
        self.assertIsNone(self.gate(self.requester), 'the approved request lets the button run')
        self.assertEqual(request.state, 'done')
        self.assertTrue(self.gate(self.requester), 'the next click asks again')
        self.assertNotEqual(self.request_of(), request)

    def test_approver_clicking_runs_at_once(self):
        self.assertIsNone(self.gate(self.approver))
        self.assertEqual(self.request_of().state, 'done')

    def test_approver_clicking_asks_somebody_else(self):
        self.flow.self_approve = False
        self.approvers.user_ids = [Command.link(self.director.id)]
        self.assertTrue(self.gate(self.approver))
        self.assertEqual(self.request_of().approver_user_ids, self.director)

    def test_domain_of_the_flow(self):
        self.flow.domain = "[('name', 'ilike', 'Big')]"
        small = self.env['res.partner'].create({'name': 'Small Customer'})
        self.assertIsNone(self.gate(self.requester, small))
        self.assertFalse(self.request_of(small))
        self.assertTrue(self.gate(self.requester))

    def test_steps_in_turn_and_conditions(self):
        self.flow.step_ids = [
            Command.create({'name': 'Director', 'sequence': 20, 'approver_type': 'user',
                            'user_ids': [Command.link(self.director.id)]}),
            Command.create({'name': 'Never', 'sequence': 30, 'approver_type': 'user',
                            'user_ids': [Command.link(self.director.id)], 'domain': "[('name', '=', 'Nobody')]"}),
        ]
        self.gate(self.requester)
        request = self.request_of()
        self.assertEqual(request.line_ids.mapped('name'), ['Approvers', 'Director'])
        with self.assertRaises(UserError):
            request.with_user(self.director).action_approve()
        request.with_user(self.approver).action_approve()
        self.assertEqual((request.state, request.approver_user_ids), ('to_approve', self.director))
        request.with_user(self.director).action_approve()
        self.assertEqual(request.state, 'done')

    def test_refuse(self):
        self.gate(self.requester)
        request = self.request_of()
        self.env['approval.decide'].with_user(self.approver).create(
            {'request_id': request.id, 'decision': 'refuse', 'note': 'Still has open invoices'}).action_confirm()
        self.assertEqual(request.state, 'refused')
        self.assertEqual(request.line_ids.note, 'Still has open invoices')
        self.assertTrue(self.partner.active)
        self.assertTrue(self.gate(self.requester), 'a refused request is asked again')
        self.assertNotEqual(self.request_of(), request)

    def test_withdraw(self):
        self.gate(self.requester)
        request = self.request_of()
        with self.assertRaises(UserError):
            request.with_user(self.approver).action_cancel()
        request.with_user(self.requester).action_cancel()
        self.assertEqual(request.state, 'cancel')
        self.assertFalse(request.activity_ids)

    def test_field_approver(self):
        self.partner.user_id = self.director
        self.flow.step_ids = [Command.clear(), Command.create({
            'name': 'Salesperson', 'approver_type': 'field', 'field_path': 'user_id'})]
        self.gate(self.requester)
        self.assertEqual(self.request_of().approver_user_ids, self.director)
        with self.assertRaises(ValidationError):
            self.flow.step_ids.field_path = 'name'

    def test_nobody_found(self):
        self.approvers.user_ids = [Command.clear()]
        self.gate(self.requester)
        admins = self.env.ref('om_approval.group_approval_manager').all_user_ids.filtered(lambda u: not u.share)
        self.assertEqual(self.request_of().approver_user_ids, admins)

    def test_access(self):
        self.gate(self.requester)
        request = self.request_of()
        Request = self.env['approval.request']
        self.assertIn(request, Request.with_user(self.requester).search([]))
        self.assertIn(request, Request.with_user(self.approver).search([('approver_user_ids', 'in', self.approver.id)]))
        self.assertNotIn(request, Request.with_user(self.director).search([]))

    def test_list_buttons(self):
        buttons = self.env['approval.button']._sync('res.users')
        self.assertTrue(buttons)
        for button in buttons:
            self.assertTrue(callable(getattr(self.env['res.users'], button.method)), button.method)

    def test_flow_needs_a_button(self):
        with self.assertRaises(ValidationError):
            self.env['approval.rule'].create({
                'name': 'No button', 'model_id': self.env['ir.model']._get_id('res.partner')})


@tagged('post_install', '-at_install')
class TestButtonRuleWebClient(HttpCase):
    """ The button clicked in the web client is stopped by the server. """

    def test_call_button(self):
        new_test_user(self.env, 'om_web_requester', password='om_web_requester',
                      groups='base.group_user,base.group_partner_manager')
        approvers = self.env['res.groups'].create({'name': 'Web Approvers'})
        button = self.env['approval.button'].create({
            'model_id': self.env['ir.model']._get_id('res.partner'), 'method': 'action_archive', 'name': 'Archive'})
        self.env['approval.rule'].create({
            'name': 'Archive', 'model_id': button.model_id.id, 'button_id': button.id, 'request_note': 'none',
            'step_ids': [Command.create({'name': 'Approvers', 'approver_type': 'group', 'group_id': approvers.id})],
        })
        partner = self.env['res.partner'].create({'name': 'Web Customer'})
        self.authenticate('om_web_requester', 'om_web_requester')
        for route in ('/web/dataset/call_button/res.partner/action_archive', '/web/dataset/call_kw'):
            response = self.url_open(route, data=json.dumps({'params': {
                'model': 'res.partner', 'method': 'action_archive', 'args': [[partner.id]], 'kwargs': {}}}),
                headers={'Content-Type': 'application/json'})
            result = response.json()
            self.assertNotIn('error', result, result)
            self.assertEqual(result['result']['tag'], 'display_notification')
        self.assertTrue(partner.active)
        self.assertEqual(self.env['approval.request'].search_count([('res_id', '=', partner.id),
                                                                      ('res_model', '=', 'res.partner')]), 1)
