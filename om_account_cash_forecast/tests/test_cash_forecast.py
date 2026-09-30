import unittest
from datetime import date

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCashForecast(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = cls.company_data['default_journal_bank']
        # opening cash
        move = cls.env['account.move'].create({
            'journal_id': cls.company_data['default_journal_misc'].id,
            'date': '2026-01-31',
            'line_ids': [
                Command.create({'name': 'capital', 'account_id': cls.bank.default_account_id.id, 'balance': 5000.0}),
                Command.create({'name': 'capital', 'account_id': cls.company_data['default_account_revenue'].id,
                                'balance': -5000.0}),
            ],
        })
        move.action_post()

    def _invoice(self, move_type, amount, due, post=True):
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.partner_a.id,
            'invoice_date': '2026-01-15',
            'invoice_payment_term_id': False,
            'invoice_line_ids': [Command.create({'name': 'item', 'price_unit': amount, 'tax_ids': []})],
        })
        move.invoice_date_due = due
        if post:
            move.action_post()
        return move

    def _forecast(self, **values):
        wizard = self.env['account.cash.forecast.report'].create({
            'date_from': date(2026, 2, 1), 'period_count': 3, **values,
        })
        return wizard, self.env['report.om_account_cash_forecast.report_cash_forecast']._get_forecast(wizard)

    @staticmethod
    def _rows(forecast):
        return {row['key']: row['amounts'] for section in forecast['sections'] for row in section['rows']}

    def test_forecast_by_month(self):
        self._invoice('out_invoice', 1000.0, date(2026, 2, 20))
        self._invoice('out_invoice', 300.0, date(2026, 1, 20))  # overdue
        self._invoice('in_invoice', 800.0, date(2026, 3, 10))
        self._invoice('in_invoice', 50.0, date(2026, 3, 10), post=False)
        self._invoice('out_invoice', 999.0, date(2026, 9, 1))  # beyond the forecast
        self.env['account.cash.forecast.item'].create([{
            'name': 'Salaries', 'direction': 'out', 'amount': 2000.0, 'date': date(2026, 1, 28),
            'recurrence': 'monthly',
        }, {
            'name': 'Loan received', 'direction': 'in', 'amount': 10000.0, 'date': date(2026, 4, 5),
        }])

        wizard, forecast = self._forecast()
        self.assertEqual(forecast['columns'], ['Overdue', 'Feb 2026', 'Mar 2026', 'Apr 2026'])
        self.assertEqual(self._rows(forecast), {
            'customers': [300.0, 1000.0, 0.0, 0.0],
            'suppliers': [0.0, 0.0, -800.0, 0.0],
            'expected_out': [0.0, -2000.0, -2000.0, -2000.0],
            'expected_in': [0.0, 0.0, 0.0, 10000.0],
        })
        self.assertEqual(forecast['opening'][0], 5000.0)
        self.assertEqual(forecast['closing'], [5300.0, 4300.0, 1500.0, 9500.0])

        # without the overdue, with the drafts, by partner
        wizard, forecast = self._forecast(overdue='exclude', include_drafts=True, display_partners=True)
        rows = self._rows(forecast)
        self.assertEqual(forecast['columns'], ['Feb 2026', 'Mar 2026', 'Apr 2026'])
        self.assertEqual(rows['customers'], [1000.0, 0.0, 0.0])
        self.assertEqual(rows['suppliers'], [0.0, -850.0, 0.0])
        customers = next(row for row in forecast['sections'][0]['rows'] if row['key'] == 'customers')
        self.assertEqual([partner['total'] for partner in customers['partners']], [1000.0])

        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_cash_forecast.report_cash_forecast', wizard.ids)[0].decode()
        self.assertIn('Cash Forecast', html)
        self.assertIn('Vendor bills', html)

    def test_weeks_and_negative_balance(self):
        self._invoice('in_invoice', 7000.0, date(2026, 2, 9))
        wizard, forecast = self._forecast(period_type='week', period_count=2, overdue='exclude')
        self.assertEqual(len(forecast['columns']), 2)
        self.assertEqual(self._rows(forecast)['suppliers'], [0.0, -7000.0])
        self.assertEqual(forecast['lowest'], -2000.0)
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_cash_forecast.report_cash_forecast', wizard.ids)[0].decode()
        self.assertIn('expected to go negative', html)

    def test_recurring_items(self):
        item = self.env['account.cash.forecast.item'].create({
            'name': 'Rent', 'amount': 100.0, 'date': date(2026, 1, 31), 'recurrence': 'monthly',
            'date_end': date(2026, 4, 30),
        })
        self.assertEqual(item._get_occurrences(date(2026, 2, 1), date(2026, 12, 31)),
                         [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])

    def test_print_action(self):
        wizard = self.env['account.cash.forecast.report'].create({'date_from': date(2026, 2, 1)})
        action = wizard.action_print()
        self.assertEqual(action['report_name'], 'om_account_cash_forecast.report_cash_forecast')

    def test_recurring_payments(self):
        if 'recurring.payment.line' not in self.env:
            raise unittest.SkipTest('om_recurring_payments is not installed')
        template = self.env['account.recurring.template'].create({
            'name': 'Monthly', 'journal_id': self.bank.id, 'recurring_period': 'months', 'recurring_interval': 1,
            'journal_state': 'posted', 'state': 'done',
        })
        for payment_type, amount in (('inbound', 400.0), ('outbound', 150.0)):
            self.env['recurring.payment'].create({
                'template_id': template.id, 'partner_id': self.partner_a.id, 'amount': amount,
                'payment_type': payment_type, 'date_begin': '2026-02-15', 'date_end': '2026-03-31',
            }).action_done()
        _wizard, forecast = self._forecast(overdue='exclude')
        rows = self._rows(forecast)
        self.assertEqual(rows['recurring_in'], [400.0, 400.0, 0.0])
        self.assertEqual(rows['recurring_out'], [-150.0, -150.0, 0.0])
