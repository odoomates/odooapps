from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestDailyBooks(AccountTestInvoicingCommon):

    def test_default_dates_follow_today(self):
        for model in ('account.daybook.report', 'account.cashbook.report', 'account.bankbook.report'):
            for today in ('2026-01-15', '2026-03-02'):
                with self.subTest(model=model, today=today), freeze_time(today):
                    wizard = self.env[model].create({})
                    self.assertEqual(str(wizard.date_from), today)
                    self.assertEqual(str(wizard.date_to), today)
                    self.assertEqual(wizard.journal_ids.company_id, self.env.company)

    def test_day_book_all_entries_without_cancelled(self):
        posted = self.init_invoice('out_invoice', amounts=[100.0], invoice_date='2026-02-10', post=True)
        draft = self.init_invoice('out_invoice', amounts=[200.0], invoice_date='2026-02-10')
        cancelled = self.init_invoice('out_invoice', amounts=[400.0], invoice_date='2026-02-10')
        cancelled.button_cancel()
        wizard = self.env['account.daybook.report'].create({
            'date_from': '2026-02-10', 'date_to': '2026-02-10', 'target_move': 'all',
        })
        # what `check_report` sends to the report (another module may show the report on screen instead)
        data = {'form': wizard.read(['target_move', 'date_from', 'date_to', 'journal_ids', 'account_ids'])[0]}
        data['form']['comparison_context'] = wizard._build_comparison_context(data)
        values = self.env['report.om_account_daily_reports.report_daybook'].with_context(
            active_model=wizard._name, active_ids=wizard.ids)._get_report_values(wizard.ids, data)
        moves = {line['mmove_id'] for day in values['Accounts'] for line in day['move_lines']}
        self.assertIn(posted.id, moves)
        self.assertIn(draft.id, moves)
        self.assertNotIn(cancelled.id, moves)

    # ------------------------------------------------------------------
    # report data and rendering of each book
    # ------------------------------------------------------------------

    def _entry(self, journal, date, amount, debit_account, credit_account, post=True, ref=False):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': journal.id, 'date': date, 'ref': ref,
            'line_ids': [
                Command.create({'account_id': debit_account.id, 'debit': amount, 'name': 'debit line'}),
                Command.create({'account_id': credit_account.id, 'credit': amount, 'name': 'credit line'}),
            ],
        })
        if post:
            move.action_post()
        return move

    def _book_values(self, wizard, fields_list, report_name):
        data = {'form': wizard.read(fields_list)[0]}
        data['form']['comparison_context'] = wizard._build_comparison_context(data)
        report = self.env[f'report.{report_name}'].with_context(active_model=wizard._name, active_ids=wizard.ids)
        values = report._get_report_values(wizard.ids, data)
        self.env.company.external_report_layout_id = self.env.ref('web.external_layout_standard')
        html = self.env['ir.actions.report'].with_context(
            active_model=wizard._name, active_ids=wizard.ids,
        )._render_qweb_html(report_name, wizard.ids, data=data)[0].decode()
        return values, html

    def test_day_book_lines_and_totals_per_day(self):
        misc = self.company_data['default_journal_misc']
        revenue = self.company_data['default_account_revenue']
        expense = self.company_data['default_account_expense']
        receivable = self.company_data['default_account_receivable']
        first = self._entry(misc, '2026-04-01', 100.0, receivable, revenue, ref='DB-FIRST')
        second = self._entry(misc, '2026-04-02', 40.0, expense, receivable)
        draft = self._entry(misc, '2026-04-02', 500.0, expense, receivable, post=False)
        later = self._entry(misc, '2026-04-03', 900.0, expense, receivable)
        wizard = self.env['account.daybook.report'].create({'date_from': '2026-04-01', 'date_to': '2026-04-02'})

        values, html = self._book_values(
            wizard, ['target_move', 'date_from', 'date_to', 'journal_ids', 'account_ids'],
            'om_account_daily_reports.report_daybook')
        days = {str(day['date']): day for day in values['Accounts']}
        self.assertEqual(sorted(days), ['2026-04-01', '2026-04-02'])
        self.assertEqual({line['mmove_id'] for line in days['2026-04-01']['move_lines']}, {first.id})
        # the draft entry is left out of the posted entries, the later one is out of the period
        self.assertEqual({line['mmove_id'] for line in days['2026-04-02']['move_lines']}, {second.id})
        self.assertNotIn(draft.id, [line['mmove_id'] for day in days.values() for line in day['move_lines']])
        self.assertNotIn(later.id, [line['mmove_id'] for day in days.values() for line in day['move_lines']])
        self.assertEqual((days['2026-04-01']['debit'], days['2026-04-01']['credit'], days['2026-04-01']['balance']),
                         (100.0, 100.0, 0.0))
        self.assertEqual((days['2026-04-02']['debit'], days['2026-04-02']['credit']), (40.0, 40.0))
        self.assertIn(misc.code, values['print_journal'])

        self.assertIn('Day Book', html)
        self.assertIn(first.name, html)
        self.assertIn('DB-FIRST', html)
        self.assertNotIn(later.name, html)

    def test_cash_book_lines_initial_and_running_balance(self):
        cash_journal = self.company_data['default_journal_cash']
        cash = cash_journal.default_account_id
        revenue = self.company_data['default_account_revenue']
        expense = self.company_data['default_account_expense']
        opening = self._entry(cash_journal, '2026-04-30', 1000.0, cash, revenue)
        sale = self._entry(cash_journal, '2026-05-02', 300.0, cash, revenue)
        spend = self._entry(cash_journal, '2026-05-05', 50.0, expense, cash)
        self._entry(cash_journal, '2026-05-06', 700.0, cash, revenue, post=False)
        wizard = self.env['account.cashbook.report'].create({
            'date_from': '2026-05-01', 'date_to': '2026-05-31', 'initial_balance': True,
        })
        self.assertIn(cash, wizard.account_ids)

        values, html = self._book_values(
            wizard, ['target_move', 'date_from', 'date_to', 'journal_ids', 'account_ids', 'sortby',
                     'initial_balance', 'display_account'],
            'om_account_daily_reports.report_cashbook')
        cash_rows = [row for row in values['Accounts'] if row['code'] == cash.code]
        self.assertEqual(len(cash_rows), 1)
        row = cash_rows[0]
        lines = row['move_lines']
        self.assertEqual([line['lname'] for line in lines], ['Initial Balance', 'debit line', 'credit line'])
        self.assertEqual([line['move_name'] for line in lines[1:]], [sale.name, spend.name])
        # the balance of each line runs from the initial balance, the draft entry is not counted
        self.assertEqual([line['balance'] for line in lines], [1000.0, 1300.0, 1250.0])
        self.assertEqual((row['debit'], row['credit'], row['balance']), (1300.0, 50.0, 1250.0))
        # the revenue and expense accounts are not cash accounts
        self.assertNotIn(revenue.code, [row['code'] for row in values['Accounts']])
        self.assertNotIn(opening.name, [line['move_name'] for line in lines])

        self.assertIn('Cash Book', html)
        self.assertIn(sale.name, html)
        self.assertIn('Initial Balance', html)

    def test_bank_book_lines_and_totals(self):
        bank_journal = self.company_data['default_journal_bank']
        bank = bank_journal.default_account_id
        revenue = self.company_data['default_account_revenue']
        expense = self.company_data['default_account_expense']
        cash_journal = self.company_data['default_journal_cash']
        before = self._entry(bank_journal, '2026-05-20', 5000.0, bank, revenue)
        received = self._entry(bank_journal, '2026-06-03', 250.0, bank, revenue)
        paid = self._entry(bank_journal, '2026-06-10', 75.0, expense, bank)
        cash_sale = self._entry(cash_journal, '2026-06-04', 60.0, cash_journal.default_account_id, revenue)
        wizard = self.env['account.bankbook.report'].create({
            'date_from': '2026-06-01', 'date_to': '2026-06-30', 'sortby': 'sort_journal_partner',
        })
        self.assertIn(bank, wizard.account_ids)
        self.assertNotIn(cash_journal.default_account_id, wizard.account_ids)

        values, html = self._book_values(
            wizard, ['target_move', 'date_from', 'date_to', 'journal_ids', 'account_ids', 'sortby',
                     'initial_balance', 'display_account'],
            'om_account_daily_reports.report_bankbook')
        self.assertEqual([row['code'] for row in values['Accounts']], [bank.code],
                         'only the bank accounts with movements are listed')
        row = values['Accounts'][0]
        # without the initial balance the entry of May is left out
        self.assertEqual([line['move_name'] for line in row['move_lines']], [received.name, paid.name])
        self.assertEqual([line['balance'] for line in row['move_lines']], [250.0, 175.0])
        self.assertEqual((row['debit'], row['credit'], row['balance']), (250.0, 75.0, 175.0))

        self.assertIn('Bank Book', html)
        self.assertIn(received.name, html)
        self.assertIn(paid.name, html)
        self.assertNotIn(before.name, html)
        self.assertNotIn(cash_sale.name, html)
