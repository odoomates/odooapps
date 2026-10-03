from odoo import fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestReportFixes(AccountTestInvoicingCommon):

    def _receivable_debit(self, state):
        """ :return: the debit of the receivable of partner_a the reports see for `state` """
        tables, where_clause, where_params = self.env['account.move.line'].with_context(
            state=state, company_id=self.env.company.id)._query_get()
        self.env.cr.execute(
            'SELECT COALESCE(SUM("account_move_line".debit), 0) FROM ' + tables
            + ' WHERE "account_move_line".partner_id = %s AND "account_move_line".account_id = %s AND '
            + where_clause,
            [self.partner_a.id, self.company_data['default_account_receivable'].id] + where_params)
        return self.env.cr.fetchone()[0]

    def test_all_entries_leave_out_the_cancelled_ones(self):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-06-01', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[40.0], taxes=[],
                          invoice_date='2025-06-01')
        cancelled = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[1000.0], taxes=[],
                                      invoice_date='2025-06-01', post=True)
        cancelled.button_draft()
        cancelled.button_cancel()
        self.env.flush_all()

        self.assertEqual(self._receivable_debit('all'), 140.0, 'draft and posted, never cancelled')
        self.assertEqual(self._receivable_debit('posted'), 100.0)

    def _partner_ledger(self, **form):
        wizard = self.env['account.report.partner.ledger'].create(dict({'target_move': 'all'}, **form))
        data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
        report = self.env['report.accounting_pdf_reports.report_partnerledger']
        values = report._get_report_values(wizard.ids, data)
        return report, values['data'], values

    def test_partner_ledger_totals_with_an_initial_balance(self):
        """ With a start date the domain joins the accounts, the totals still sum the journal items """
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-06-01', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[30.0], taxes=[],
                          invoice_date='2025-08-01', post=True)

        report, data, _values = self._partner_ledger(date_from='2025-07-01', date_to='2025-12-31')
        lines = report._lines(data, self.partner_a)

        self.assertTrue(lines)
        self.assertEqual(report._sum_partner(data, self.partner_a, 'debit'), sum(l['debit'] for l in lines))
        self.assertEqual(report._sum_partner(data, self.partner_a, 'credit'), 0.0)
        self.assertEqual(report._sum_partner(data, self.partner_a, 'debit - credit'), lines[-1]['progress'])
        self.assertIsNone(report._sum_partner(data, self.partner_a, 'debit; SELECT 1'))

    def test_partner_ledger_does_not_repeat_the_move_name(self):
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                                    invoice_date='2025-06-01', post=True)
        invoice.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable').name = invoice.name

        report, data, _values = self._partner_ledger()

        self.assertEqual([line['displayed_name'] for line in report._lines(data, self.partner_a)], [invoice.name])

    def test_the_wizards_default_to_the_local_day(self):
        today = fields.Date.to_date(self.env['account.aged.trial.balance'].default_get(['date_from'])['date_from'])
        # the tax report opens on the month of the local day
        month_start = self.env['account.tax.report.wizard'].default_get(['date_from'])['date_from']
        self.assertEqual(str(month_start), str(today.replace(day=1)))
