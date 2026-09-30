from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestRecurringPayment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.template = cls._create_template()

    @classmethod
    def _create_template(cls, **vals):
        return cls.env['account.recurring.template'].create({
            'name': 'Monthly',
            'journal_id': cls.bank_journal.id,
            'recurring_period': 'months',
            'recurring_interval': 1,
            'journal_state': 'posted',
            'state': 'done',
            **vals,
        })

    def _create_recurring_payment(self, **vals):
        return self.env['recurring.payment'].create({
            'template_id': self.template.id,
            'partner_id': self.partner_a.id,
            'amount': 100.0,
            'date_begin': '2026-01-01',
            'date_end': '2026-03-31',
            **vals,
        })

    def test_interval_must_be_positive(self):
        for interval in (0, -1):
            with self.subTest(interval=interval), self.assertRaises(ValidationError):
                self._create_template(recurring_interval=interval)

        # a template saved before the constraint existed must not hang the confirmation
        recurring_payment = self._create_recurring_payment()
        self.env.cr.execute("UPDATE account_recurring_template SET recurring_interval = 0 WHERE id = %s",
                            [self.template.id])
        self.env.invalidate_all()
        with self.assertRaises(UserError):
            recurring_payment.action_done()

    def test_journal_change_stays_on_the_payment(self):
        other_journal = self.bank_journal.copy({'name': 'Second Bank', 'code': 'BNK2'})
        payment_1 = self._create_recurring_payment()
        payment_2 = self._create_recurring_payment()
        self.assertEqual(payment_1.journal_id, self.bank_journal)

        payment_1.journal_id = other_journal
        self.assertEqual(payment_1.journal_id, other_journal)
        self.assertEqual(self.template.journal_id, self.bank_journal)
        self.assertEqual(payment_2.journal_id, self.bank_journal)

    def test_payment_direction_sets_partner_type(self):
        for payment_type, partner_type, account_type in (
            ('outbound', 'supplier', 'liability_payable'),
            ('inbound', 'customer', 'asset_receivable'),
        ):
            with self.subTest(payment_type=payment_type):
                recurring_payment = self._create_recurring_payment(payment_type=payment_type, date_end='2026-01-01')
                recurring_payment.action_done()
                recurring_payment.line_ids.action_create_payment()
                payment = recurring_payment.line_ids.payment_id
                self.assertEqual(payment.payment_type, payment_type)
                self.assertEqual(payment.partner_type, partner_type)
                self.assertEqual(payment.destination_account_id.account_type, account_type)
                self.assertNotEqual(payment.state, 'draft')

    def test_create_several_records(self):
        recurring_payments = self.env['recurring.payment'].create([{
            'template_id': self.template.id,
            'partner_id': self.partner_a.id,
            'amount': amount,
            'date_begin': '2026-01-01',
            'date_end': '2026-03-31',
        } for amount in (10.0, 20.0, 30.0)])
        self.assertEqual(recurring_payments.mapped('amount'), [10.0, 20.0, 30.0])
        self.assertEqual(len(set(recurring_payments.mapped('name'))), 3)

    def test_cron_continues_after_a_failing_line(self):
        failing = self._create_recurring_payment(date_end='2026-01-01')
        failing.action_done()
        failing.line_ids.journal_id = self.company_data['default_journal_sale']
        working = self._create_recurring_payment(date_end='2026-01-01')
        working.action_done()

        with self.assertLogs('odoo.addons.om_recurring_payments.models.recurring_payment', 'WARNING') as logs:
            self.env['recurring.payment'].action_generate_payment()
        self.assertIn(failing.name, logs.output[0])
        self.assertEqual(failing.line_ids.state, 'draft')
        self.assertFalse(failing.line_ids.payment_id)
        self.assertEqual(working.line_ids.state, 'done')
        self.assertTrue(working.line_ids.payment_id)

    def test_write_amount_on_several_records(self):
        recurring_payments = self._create_recurring_payment() | self._create_recurring_payment()
        recurring_payments.write({'amount': 50.0})
        self.assertEqual(recurring_payments.mapped('amount'), [50.0, 50.0])
        with self.assertRaises(ValidationError):
            recurring_payments.write({'amount': 0.0})

    def test_end_date_is_included(self):
        recurring_payment = self._create_recurring_payment(date_end='2026-12-01')
        recurring_payment.action_done()
        self.assertEqual(len(recurring_payment.line_ids), 12)
        self.assertEqual(max(recurring_payment.line_ids.mapped('date')), date(2026, 12, 1))

        single_day = self._create_recurring_payment(date_begin='2026-05-01', date_end='2026-05-01')
        single_day.action_done()
        self.assertEqual(len(single_day.line_ids), 1)

        with self.assertRaises(ValidationError):
            self._create_recurring_payment(date_begin='2026-12-31', date_end='2026-01-01')

    def test_multi_company(self):
        company_2 = self.company_data_2['company']
        journal_2 = self.company_data_2['default_journal_bank']
        with self.assertRaises(UserError):
            self._create_template(company_id=company_2.id)

        template_2 = self._create_template(company_id=company_2.id, journal_id=journal_2.id)
        recurring_payment = self._create_recurring_payment(template_id=template_2.id, date_end='2026-01-01')
        self.assertEqual(recurring_payment.company_id, company_2)
        self.assertEqual(recurring_payment.journal_id, journal_2)
        recurring_payment.action_done()
        self.assertEqual(recurring_payment.line_ids.company_id, company_2)

        self.env['recurring.payment'].action_generate_payment()
        self.assertEqual(recurring_payment.line_ids.payment_id.company_id, company_2)

        user_1 = new_test_user(
            self.env, login='company_1_accountant', groups='account.group_account_user',
            company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)],
        )
        for model, records in (('account.recurring.template', template_2), ('recurring.payment', recurring_payment),
                               ('recurring.payment.line', recurring_payment.line_ids)):
            self.assertFalse(self.env[model].with_user(user_1).search([('id', 'in', records.ids)]), model)

    def test_line_date_default_is_today(self):
        with freeze_time('2030-06-15'):
            self.assertEqual(
                self.env['recurring.payment.line'].default_get(['date'])['date'], date(2030, 6, 15))

    def test_foreign_currency(self):
        other_currency = self.setup_other_currency('EUR')
        journal = self.bank_journal.copy({'name': 'EUR Bank', 'code': 'BEUR', 'currency_id': other_currency.id})
        template = self._create_template(journal_id=journal.id)
        recurring_payment = self._create_recurring_payment(template_id=template.id, date_end='2026-01-01')
        self.assertEqual(recurring_payment.currency_id, other_currency)

        recurring_payment.action_done()
        recurring_payment.line_ids.action_create_payment()
        payment = recurring_payment.line_ids.payment_id
        self.assertEqual(payment.currency_id, other_currency)
        self.assertEqual(payment.amount, 100.0)

    def test_payment_created_once(self):
        recurring_payment = self._create_recurring_payment(date_end='2026-01-01')
        recurring_payment.action_done()
        line = recurring_payment.line_ids
        line.action_create_payment()
        payment = line.payment_id
        line.action_create_payment()
        self.env['recurring.payment'].action_generate_payment()
        self.assertEqual(line.payment_id, payment)
        self.assertEqual(self.env['account.payment'].search_count([('memo', '=', recurring_payment.name)]), 1)
