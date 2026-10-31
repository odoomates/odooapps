import json

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from .test_button_rule import ApprovalCase


@tagged('post_install', '-at_install')
class TestLock(ApprovalCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(cls.env, 'om_lock_manager',
                                    groups='base.group_user,base.group_partner_manager,om_approval.group_approval_manager')

    def tearDown(self):
        self.env['approval.request']._restore_lock()
        super().tearDown()

    def assertLocked(self, partner=None, user=None):
        partner = (partner or self.partner).with_user(user or self.requester)
        with self.assertRaises(UserError):
            partner.write({'phone': '123'})
        with self.assertRaises(UserError):
            partner.unlink()

    def assertEditable(self, partner=None, user=None):
        (partner or self.partner).with_user(user or self.requester).write({'phone': '456'})

    def test_locked_while_waiting(self):
        self.gate(self.requester)
        self.assertLocked()
        self.assertLocked(user=self.approver)
        self.assertLocked(user=self.manager)
        # the chatter still works, and the server code acting as the super user is not stopped
        self.partner.with_user(self.requester).message_post(body='Any news?')
        self.partner.sudo().write({'phone': '789'})
        # the other records are not locked
        self.assertEditable(self.env['res.partner'].create({'name': 'Other Customer'}))

    def test_unlocked_once_the_button_ran(self):
        self.gate(self.requester)
        request = self.request_of()
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, 'done')
        self.assertFalse(self.partner.active, 'the approved button changed the locked record')
        self.assertFalse(request.is_locking)
        self.assertEditable()

    def test_locked_while_approved_until_clicked_again(self):
        self.flow.run_on_approval = False
        self.gate(self.requester)
        request = self.request_of()
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, 'approved')
        self.assertLocked()
        self.assertIsNone(self.gate(self.requester))
        self.partner.with_user(self.requester).action_archive()
        self.assertFalse(self.partner.active)
        self.env['approval.request']._restore_lock()
        self.assertEditable()

    def test_kept_locked_until_unlocked(self):
        self.flow.lock_after = 'keep'
        self.gate(self.requester)
        request = self.request_of()
        self.assertTrue(request.keep_locked)
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, 'done')
        self.assertFalse(self.partner.active, 'the button ran although the record stays locked')
        self.assertTrue(request.is_locking)
        self.assertLocked()
        with self.assertRaises(UserError):
            request.with_user(self.requester).action_unlock()
        request.with_user(self.manager).action_unlock()
        self.assertEqual(request.unlocked_by_id, self.manager)
        self.assertFalse(request.is_locking)
        self.assertEditable()

    def test_kept_locked_when_clicked_again(self):
        self.flow.write({'lock_after': 'keep', 'run_on_approval': False})
        self.gate(self.requester)
        self.request_of().with_user(self.approver).action_approve()
        self.assertIsNone(self.gate(self.requester))
        self.partner.with_user(self.requester).action_archive()
        self.env['approval.request']._restore_lock()
        self.assertLocked()

    def test_unlocked_when_refused_or_withdrawn(self):
        self.gate(self.requester)
        request = self.request_of()
        request.with_user(self.approver).action_refuse('No')
        self.assertEditable()
        self.gate(self.requester)
        self.assertLocked()
        self.request_of().with_user(self.requester).action_cancel()
        self.assertEditable()

    def test_flow_not_locking(self):
        self.flow.lock_record = False
        self.assertNotIn('res.partner', self.env['approval.rule']._locked_models())
        self.gate(self.requester)
        self.assertFalse(self.request_of().lock_record)
        self.assertEditable()
        self.flow.lock_record = True
        self.assertIn('res.partner', self.env['approval.rule']._locked_models())
        self.assertEditable()  # a request asked without the lock does not lock afterwards

    def test_record_approvals(self):
        self.gate(self.requester)
        Request = self.env['approval.request']
        info = Request.with_user(self.requester).get_record_approvals('res.partner', self.partner.id)
        self.assertTrue(info['locked'])
        [item] = info['requests']
        self.assertEqual((item['step'], item['approvers']), ('Approvers', [self.approver.name]))
        self.assertTrue(item['can_withdraw'])
        self.assertFalse(item['can_approve'])
        item = Request.with_user(self.approver).get_record_approvals('res.partner', self.partner.id)['requests'][0]
        self.assertTrue(item['can_approve'])
        self.assertFalse(item['can_withdraw'])
        item = Request.with_user(self.director).get_record_approvals('res.partner', self.partner.id)['requests'][0]
        self.assertFalse(item['can_open'] or item['lines'], 'who takes no part sees only that it waits')
        self.assertIn('res.partner', Request.get_approval_models())
        self.request_of().with_user(self.approver).action_approve()
        self.assertEqual(Request.get_record_approvals('res.partner', self.partner.id)['requests'], [])

    def test_summary(self):
        self.flow.write({
            'domain': "[('name', 'ilike', 'Big')]",
            'self_approve': False,
            'lock_after': 'keep',
            'step_ids': [Command.create({'name': 'Director', 'sequence': 20, 'approver_type': 'user',
                                         'user_ids': [Command.link(self.director.id)], 'remind_days': 1,
                                         'domain': "[('name', 'ilike', 'Customer')]"})],
        })
        summary = str(self.flow.summary)
        for text in ('Archive', 'Contact', 'Name contains Big', 'users of the group Partner Approvers', 'Director',
                     self.director.name, 'only when', 'reminded after 1 day', 'does not approve their own',
                     'runs by itself', 'until an approval manager unlocks it'):
            self.assertIn(text, summary)

    def test_simulate(self):
        self.flow.step_ids = [Command.create({'name': 'Never', 'sequence': 20, 'approver_type': 'user',
                                              'user_ids': [Command.link(self.director.id)],
                                              'domain': "[('name', '=', 'Nobody')]"})]
        wizard = self.env['approval.simulate'].create({
            'flow_id': self.flow.id, 'record_ref': 'res.partner,%s' % self.partner.id, 'user_id': self.requester.id})
        result = str(wizard.result)
        self.assertIn(self.approver.name, result)
        self.assertIn('Skipped', result)
        self.assertIn('read-only', result)
        self.assertFalse(self.request_of(), 'testing asks nothing')
        self.flow.domain = "[('name', '=', 'Nobody')]"
        wizard.flow_id = self.flow  # computes again
        self.assertIn('does not apply', str(wizard.result))


@tagged('post_install', '-at_install')
class TestLockWebClient(HttpCase):
    """ The approved button clicked again in the web client changes its record, which stays locked afterwards. """

    def rpc(self, route, model, method, args):
        response = self.url_open(route, data=json.dumps({'params': {
            'model': model, 'method': method, 'args': args, 'kwargs': {}}}),
            headers={'Content-Type': 'application/json'})
        return response.json()

    def test_click_again_then_locked(self):
        new_test_user(self.env, 'om_lock_web', password='om_lock_web',
                      groups='base.group_user,base.group_partner_manager')
        approver = new_test_user(self.env, 'om_lock_web_approver')
        button = self.env['approval.button'].create({
            'model_id': self.env['ir.model']._get_id('res.partner'), 'method': 'action_archive', 'name': 'Archive'})
        self.env['approval.rule'].create({
            'name': 'Archive', 'model_id': button.model_id.id, 'button_id': button.id, 'run_on_approval': False,
            'lock_after': 'keep', 'request_note': 'none',
            'step_ids': [Command.create({'name': 'Approver', 'approver_type': 'user',
                                         'user_ids': [Command.link(approver.id)]})],
        })
        partner = self.env['res.partner'].create({'name': 'Web Customer'})
        self.authenticate('om_lock_web', 'om_lock_web')
        route = '/web/dataset/call_button/res.partner/action_archive'
        self.assertEqual(self.rpc(route, 'res.partner', 'action_archive', [[partner.id]])['result']['tag'],
                         'display_notification')
        with mute_logger('odoo.http'):
            result = self.rpc('/web/dataset/call_kw', 'res.partner', 'write', [[partner.id], {'phone': '1'}])
        self.assertIn('locked', result['error']['data']['message'])
        request = self.env['approval.request'].search([('res_model', '=', 'res.partner'), ('res_id', '=', partner.id)])
        request.with_user(approver).action_approve()
        result = self.rpc(route, 'res.partner', 'action_archive', [[partner.id]])
        self.assertNotIn('error', result, result)
        partner.invalidate_recordset()
        self.assertFalse(partner.active)
        with mute_logger('odoo.http'):
            result = self.rpc('/web/dataset/call_kw', 'res.partner', 'write', [[partner.id], {'phone': '2'}])
        self.assertIn('locked', result['error']['data']['message'], 'kept locked once the button ran')


@tagged('post_install', '-at_install')
class TestLockTour(HttpCase):

    def test_banner(self):
        """ The approver opens the locked record: the banner, the read-only form, and Approve. """
        group = self.env['res.groups'].create({'name': 'Tour Approvers', 'user_ids': [
            Command.link(self.env.ref('base.user_admin').id)]})
        button = self.env['approval.button'].create({
            'model_id': self.env['ir.model']._get_id('res.partner'), 'method': 'action_archive', 'name': 'Archive'})
        self.env['approval.rule'].create({
            'name': 'Archive', 'model_id': button.model_id.id, 'button_id': button.id, 'self_approve': False,
            'request_note': 'none',
            'step_ids': [Command.create({'name': 'Tour Approvers', 'approver_type': 'group', 'group_id': group.id})],
        })
        partner = self.env['res.partner'].create({'name': 'Tour Customer'})
        requester = new_test_user(self.env, 'om_lock_tour', groups='base.group_user,base.group_partner_manager')
        self.env['approval.request'].with_user(requester)._gate_button('res.partner', 'action_archive', partner.ids)
        self.start_tour(f'/odoo/res.partner/{partner.id}', 'om_approval_banner', login='admin')
        self.assertFalse(partner.active)
