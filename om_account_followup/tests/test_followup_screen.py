from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
@freeze_time('2026-03-01')
class TestFollowupScreen(AccountTestInvoicingCommon):
    """ The follow-up status of the customers, the reminders sent from the screen and the controls per customer. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.external_report_layout_id = cls.env.ref('web.external_layout_standard')
        cls.customer = cls.env['res.partner'].create({'name': 'Late Payer', 'email': 'late.payer@example.com'})
        cls.plan = cls.env['followup.followup'].create({
            'name': 'Standard', 'company_id': cls.company.id, 'is_default': True,
            'followup_line': [
                Command.create({'name': 'First reminder', 'delay': 10, 'send_email': True, 'send_letter': False}),
                Command.create({'name': 'Second reminder', 'delay': 30, 'send_email': True, 'send_letter': True}),
            ],
        })
        cls.first, cls.second = cls.plan._get_levels()

    def _invoice(self, due_date, amount=1000.0, partner=None):
        invoice = self.init_invoice('out_invoice', partner=partner or self.customer, invoice_date=due_date,
                                    amounts=[amount], taxes=[], post=False)
        invoice.invoice_payment_term_id = False
        invoice.invoice_date_due = due_date
        invoice.action_post()
        return invoice

    def _statuses(self):
        return self.env['res.partner'].search([('followup_status', '=', self.customer.followup_status),
                                               ('id', '=', self.customer.id)])

    def test_status_follows_the_plan(self):
        self.assertEqual(self.customer.followup_status, 'no_action_needed')
        self._invoice('2026-03-10')
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_status, 'no_action_needed', 'nothing overdue yet')
        self.assertEqual(self.customer.followup_next_date, date(2026, 3, 20))

        invoice = self._invoice('2026-02-25')
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_status, 'with_overdue_invoices',
                         'overdue, but the first reminder comes after 10 days')
        self.assertEqual(self.customer.followup_next_date, date(2026, 3, 7))

        invoice.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable').date_maturity = \
            date(2026, 2, 10)
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_status, 'in_need_of_action')
        self.assertEqual(self.customer.followup_level_due_id, self.first)
        self.assertEqual(self._statuses(), self.customer, 'the search agrees with the status')

        self.env['followup.send'].create({'partner_ids': [Command.set(self.customer.ids)]}).action_send()
        self.env.invalidate_all()
        self.assertEqual(self.customer.latest_followup_level_id, self.first)
        self.assertEqual(self.customer.followup_status, 'with_overdue_invoices')
        self.assertEqual(self.customer.followup_next_date, date(2026, 3, 12), 'the second reminder is next')

    def test_old_invoices_reach_the_highest_level(self):
        self._invoice('2026-01-01')
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_level_due_id, self.second)

    def test_excluded_and_promise(self):
        self._invoice('2026-01-01')
        self.customer.followup_excluded = True
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_status, 'excluded')
        self.assertEqual(self._statuses(), self.customer)
        with self.assertRaises(UserError):
            self.env['followup.send'].create({'partner_ids': [Command.set(self.customer.ids)]}).action_send()

        self.customer.action_followup_include()
        self.customer.followup_promise_date = date(2026, 3, 15)
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_status, 'promise')
        wizard = self.env['followup.print'].create({'date': '2026-03-01', 'followup_id': self.plan.id})
        self.assertFalse(wizard._get_partners_followp()['partner_ids'], 'no reminder before the promised date')
        with freeze_time('2026-03-16'):
            self.env.invalidate_all()
            self.assertEqual(self.customer.followup_status, 'in_need_of_action', 'the promise was not kept')

    def test_disputed_invoices_are_left_out(self):
        invoice = self._invoice('2026-01-01', amount=500.0)
        self._invoice('2026-03-20', amount=200.0)
        invoice.followup_disputed = True
        self.env.invalidate_all()
        self.assertEqual(self.customer.payment_amount_overdue, 0.0)
        self.assertEqual(self.customer.payment_amount_due, 200.0)
        self.assertEqual(self.customer.followup_status, 'no_action_needed')
        self.assertNotIn('500.00', self.customer.get_followup_table_html())
        stat = self.env['followup.stat'].search([('partner_id', '=', self.customer.id)])
        self.assertEqual(stat.balance, 200.0)
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_followup.report_customer_statement', self.customer.ids)[0].decode()
        self.assertIn('Disputed', html, 'the statement lists the disputed invoice, flagged')

    def test_plan_of_the_customer(self):
        strict = self.env['followup.followup'].create({
            'name': 'Strict', 'company_id': self.company.id,
            'followup_line': [Command.create({'name': 'Immediate', 'delay': 1, 'send_email': True})],
        })
        self.assertTrue(self.plan.is_default)
        self.assertFalse(strict.is_default)
        self._invoice('2026-02-25')
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_status, 'with_overdue_invoices')
        self.customer.followup_plan_id = strict
        self.env.invalidate_all()
        self.assertEqual(self.customer.followup_level_due_id.name, 'Immediate')
        self.assertEqual(strict.partner_count, 1)
        # the batch processing of a plan only sends to its customers
        wizard = self.env['followup.print'].create({'date': '2026-03-01', 'followup_id': self.plan.id})
        self.assertFalse(wizard._get_partners_followp()['partner_ids'])
        wizard = self.env['followup.print'].create({'date': '2026-03-01', 'followup_id': strict.id})
        self.assertTrue(wizard._get_partners_followp()['partner_ids'])

        strict.is_default = True
        self.assertFalse(self.plan.is_default, 'one default plan per company')
        with self.assertRaises(ValidationError):
            self.env['followup.followup'].search([('company_id', '=', self.company.id)]).write({'is_default': True})

    def test_send_reminder_dialog(self):
        invoice = self._invoice('2026-02-01', amount=1234.5)
        wizard = Form(self.env['followup.send'].with_context(
            active_model='res.partner', active_ids=self.customer.ids))
        self.assertEqual(wizard.level_id, self.first)
        self.assertTrue(wizard.send_email)
        self.assertFalse(wizard.print_letter)
        self.assertIn(self.customer, wizard.recipient_ids)
        self.assertIn('1,234.50', wizard.body)
        self.assertIn(invoice.get_portal_url(), wizard.body, 'the customer can open and pay the invoice')
        wizard.subject = 'Your overdue invoice'
        wizard.print_letter = True
        action = wizard.save().action_send()
        self.assertEqual(action['report_name'], 'om_account_followup.report_customer_statement')

        message = self.customer.message_ids.filtered(lambda m: m.subject == 'Your overdue invoice')
        self.assertIn(self.customer, message.partner_ids)
        self.assertEqual(message.attachment_ids.mapped('mimetype'), ['application/pdf'],
                         'the overdue invoice is attached')
        receivable = invoice.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')
        self.assertEqual(receivable.followup_line_id, self.first)

    def test_send_to_several_customers(self):
        other = self.env['res.partner'].create({'name': 'No Email'})
        self._invoice('2026-02-01')
        self._invoice('2026-02-01', partner=other)
        wizard = self.env['followup.send'].with_context(
            active_model='res.partner', active_ids=(self.customer | other).ids).create({})
        self.assertFalse(wizard.body, 'no preview for several customers')
        self.assertIn('No Email', wizard.warning)
        action = wizard.action_send()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('No Email', action['params']['message'])
        self.assertTrue(self.customer.message_ids.filtered(lambda m: m.subject and 'Payment Reminder' in m.subject))
        self.assertEqual(other.activity_ids.summary, 'Reminder not sent')

    def test_log_call_and_open_items(self):
        self._invoice('2026-02-01')
        action = self.customer.action_followup_log_call()
        activity = Form(self.env['mail.activity'].with_context(action['context']))
        activity.summary = 'Called'
        activity = activity.save()
        self.assertEqual(activity.activity_type_id, self.env.ref('mail.mail_activity_data_call'))
        self.assertEqual(activity.res_id, self.customer.id)
        items = self.env['account.move.line'].search(self.customer.action_followup_open_items()['domain'])
        self.assertEqual(len(items), 1)

    def test_new_company_gets_a_plan(self):
        company = self.env['res.company'].create({'name': 'Fresh Company'})
        plan = self.env['followup.followup']._get_default_plan(company)
        self.assertEqual(plan.name, 'Fresh Company')
        self.assertTrue(plan.is_default)
        self.assertEqual(plan._get_levels().filtered('manual_action').name, 'Final notice')

    def test_billing_user_reads_the_screen(self):
        billing = new_test_user(self.env, login='billing_followup', groups='account.group_account_invoice',
                                company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        self._invoice('2026-01-01')
        partners = self.env['res.partner'].with_user(billing).search(
            [('followup_status', '=', 'in_need_of_action'), ('id', '=', self.customer.id)])
        self.assertEqual(partners.followup_level_due_id, self.second)
