from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCreditLimitBlock(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'account_use_credit_limit': True, 'credit_limit_block': True})
        cls.partner_a.with_company(cls.company).credit_limit = 1000.0
        cls.accountant = new_test_user(
            cls.env, login='credit_accountant', groups='base.group_user,account.group_account_user',
            company_id=cls.company.id)

    def _invoice(self, amount, partner=None):
        return self.init_invoice('out_invoice', partner=partner or self.partner_a,
                                 invoice_date='2026-03-01', amounts=[amount])

    def test_an_invoice_over_the_limit_is_refused(self):
        invoice = self._invoice(1500.0)
        self.assertTrue(invoice.partner_credit_warning)
        with self.assertRaisesRegex(UserError, 'credit limit'):
            invoice.with_user(self.accountant).action_post()
        self.assertEqual(invoice.state, 'draft')

    def test_an_invoice_under_the_limit_is_posted(self):
        invoice = self._invoice(400.0)
        invoice.with_user(self.accountant).action_post()
        self.assertEqual(invoice.state, 'posted')

        # what is already owed counts: the next invoice goes over the limit
        second = self._invoice(900.0)
        with self.assertRaisesRegex(UserError, 'credit limit'):
            second.with_user(self.accountant).action_post()

    def test_a_manager_posts_over_the_limit_and_it_is_logged(self):
        invoice = self._invoice(1500.0)
        self.assertTrue(self.env.user.has_group('om_account_accountant.group_credit_limit_override'))
        invoice.action_post()
        self.assertEqual(invoice.state, 'posted')
        message = invoice.message_ids.filtered(lambda message: 'credit limit' in (message.body or ''))
        self.assertEqual(len(message), 1)
        self.assertEqual(message.author_id, self.env.user.partner_id)

    def test_nothing_is_blocked_without_the_setting(self):
        self.company.credit_limit_block = False
        self._invoice(1500.0).with_user(self.accountant).action_post()

        # the limits of Odoo turned off: no warning and no block either
        self.company.write({'credit_limit_block': True, 'account_use_credit_limit': False})
        invoice = self._invoice(5000.0)
        self.assertFalse(invoice.partner_credit_warning)
        invoice.with_user(self.accountant).action_post()
        self.assertEqual(invoice.state, 'posted')

    def test_only_the_customer_invoices_are_checked(self):
        bill = self.init_invoice('in_invoice', partner=self.partner_a, invoice_date='2026-03-01',
                                 amounts=[9000.0])
        bill.with_user(self.accountant).action_post()
        self.assertEqual(bill.state, 'posted')

        refund = self.init_invoice('out_refund', partner=self.partner_a, invoice_date='2026-03-01',
                                   amounts=[9000.0])
        refund.with_user(self.accountant).action_post()
        self.assertEqual(refund.state, 'posted')

    def test_a_customer_without_a_limit_is_not_blocked(self):
        partner = self.env['res.partner'].create({'name': 'No Limit', 'credit_limit': 0.0})
        self._invoice(9000.0, partner=partner).with_user(self.accountant).action_post()

    def test_a_group_of_invoices_stops_on_the_one_over_the_limit(self):
        invoices = self._invoice(400.0) | self._invoice(900.0)
        with self.assertRaisesRegex(UserError, 'credit limit'):
            invoices.with_user(self.accountant).action_post()
        self.assertEqual(set(invoices.mapped('state')), {'draft'})
