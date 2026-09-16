from freezegun import freeze_time

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
