from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.om_account_approval.models.approval_request import CLEARED


@tagged('post_install', '-at_install')
class TestAccountApproval(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data['company']
        # the accountant running the tests sets the flows up, as an approval administrator
        cls.env.user.group_ids |= cls.env.ref('om_approval.group_approval_manager')
        user_values = {'company_id': company.id, 'company_ids': [Command.set(company.ids)]}
        cls.requester = new_test_user(cls.env, 'om_acc_requester', groups='account.group_account_invoice',
                                      **user_values)
        cls.approver = new_test_user(cls.env, 'om_acc_approver', groups='account.group_account_manager',
                                     **user_values)
        cls.approvers = cls.env['res.groups'].create({
            'name': 'Bill Approvers', 'user_ids': [Command.link(cls.approver.id)]})
        cls.bill_flow = cls._flow('account.move', [('move_type', '=', 'in_invoice')])

    @classmethod
    def _flow(cls, model, domain, **values):
        Button = cls.env['approval.button']
        button = Button.search([('model', '=', model), ('method', '=', 'action_post')], limit=1) or Button.create({
            'model_id': cls.env['ir.model']._get_id(model), 'method': 'action_post', 'name': 'Post'})
        return cls.env['approval.rule'].create({
            'name': 'Above 1,000',
            'model_id': cls.env['ir.model']._get_id(model),
            'button_id': button.id,
            'domain': repr(domain),
            'amount_field': 'amount_total' if model == 'account.move' else 'amount',
            'amount_min': 1000,
            'request_note': 'none',
            'step_ids': [Command.create({'name': 'Approvers', 'approver_type': 'group',
                                         'group_id': cls.approvers.id})],
            **values,
        })

    def tearDown(self):
        self.env['approval.request']._restore_lock()
        self.env.cr.cache.pop(CLEARED, None)
        super().tearDown()

    def bill(self, amount=5000, **values):
        bill = self.init_invoice('in_invoice', amounts=[amount], invoice_date='2024-01-15')
        bill.write(values)
        return bill

    def request_of(self, record):
        return self.env['approval.request'].search([
            ('res_model', '=', record._name), ('res_id', '=', record.id)], order='id desc', limit=1)

    def test_button_asks_then_posts_once_approved(self):
        bill = self.bill()
        self.env['approval.request'].with_user(self.requester)._gate_button('account.move', 'action_post', bill.ids)
        request = self.request_of(bill)
        self.assertEqual(request.state, 'to_approve')
        self.assertIn(bill, self.env['account.move'].search([('om_approval_waiting', '=', True)]))
        request.with_user(self.approver).action_approve()
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(request.state, 'done')

    def test_post_action_of_the_list_is_stopped(self):
        bill, small = self.bill(), self.bill(amount=100)
        with self.assertRaisesRegex(UserError, 'needs an approval'):
            (bill | small).action_validate_moves_with_confirmation()
        self.assertEqual(bill.state, 'draft')
        small.action_post()
        self.assertEqual(small.state, 'posted', 'below the amount, no approval')

    def test_approval_used_once_by_any_way(self):
        self.bill_flow.run_on_approval = False
        bill = self.bill()
        self.env['approval.request'].with_user(self.requester)._gate_button('account.move', 'action_post', bill.ids)
        request = self.request_of(bill)
        request.with_user(self.approver).action_approve()
        # locked while approved, the server post still goes through and uses the approval up
        bill.action_validate_moves_with_confirmation()
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(request.state, 'done')
        bill.button_draft()
        with self.assertRaisesRegex(UserError, 'needs an approval'):
            bill.action_post()

    def test_autopost_asks_and_leaves_the_bill_aside(self):
        bill = self.bill(auto_post='at_date')
        other = self.bill(amount=100, auto_post='at_date')
        cron = self.env.ref('account.ir_cron_auto_post_draft_entry')
        with self.enter_registry_test_mode():
            cron.method_direct_trigger()
        self.env.invalidate_all()
        self.assertEqual(other.state, 'posted', 'the other entries are not held back')
        self.assertEqual(bill.state, 'draft')
        self.assertEqual(bill.auto_post, 'at_date')
        self.assertEqual(self.request_of(bill).state, 'to_approve')

    def test_register_payment_is_stopped(self):
        self._flow('account.payment', [('payment_type', '=', 'outbound')])
        bill = self.bill()
        bill.with_context(om_approval_bypass=True).action_post()
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=bill.ids).create({})
        with self.assertRaisesRegex(UserError, 'needs an approval'):
            wizard._create_payments()
