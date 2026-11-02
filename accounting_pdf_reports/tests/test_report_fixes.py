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

    def _trial_balance_lines(self, accounts, **form):
        """ :return: the lines of the trial balance of `accounts`, printed from the list of the accounts """
        wizard = self.env['account.balance.report'].create(dict({
            'target_move': 'posted',
            'journal_ids': [fields.Command.set(self.env['account.journal'].search([]).ids)],
        }, **form))
        data = wizard.with_context(active_model='account.account', active_ids=accounts.ids).check_report()['data']
        report = self.env['report.accounting_pdf_reports.report_trialbalance'].with_context(
            active_model='account.account', active_ids=accounts.ids)
        return report._get_report_values(accounts.ids, data)['Accounts']

    def _trial_balance(self, accounts, **form):
        """ :return: {code: line} of the trial balance, for accounts of one company (the other company of the
        tests has the same codes) """
        return {line['code']: line for line in self._trial_balance_lines(accounts, **form)}

    def test_trial_balance_initial_balance(self):
        """ With a start date, the balance before it: the whole history of a balance sheet account, the current
        fiscal year only for an income account; the balance at the end includes it. """
        for amount, day in ((100.0, '2024-06-01'), (40.0, '2025-03-01'), (30.0, '2025-08-01')):
            self.init_invoice('out_invoice', partner=self.partner_a, amounts=[amount], taxes=[],
                              invoice_date=day, post=True)
        accounts = self.company_data['default_account_receivable'] + self.company_data['default_account_revenue']
        receivable, revenue = accounts.mapped('code')

        lines = self._trial_balance(accounts, date_from='2025-07-01', date_to='2025-12-31', display_account='all')
        self.assertEqual(lines[receivable]['initial_balance'], 140.0)
        self.assertEqual(lines[receivable]['debit'], 30.0)
        self.assertEqual(lines[receivable]['balance'], 170.0)
        # the income of 2024 belongs to the closed year: only the 40.00 of 2025 is brought forward
        self.assertEqual(lines[revenue]['initial_balance'], -40.0)
        self.assertEqual(lines[revenue]['credit'], 30.0)
        self.assertEqual(lines[revenue]['balance'], -70.0)
        # the income of 2024 has a line of its own
        self.assertEqual(lines['']['name'], 'Result Brought Forward')
        self.assertEqual(lines['']['initial_balance'], -100.0)
        self.assertEqual(lines['']['balance'], -100.0)

        # on the first day of the fiscal year, an income account starts at zero
        lines = self._trial_balance(accounts, date_from='2025-01-01', date_to='2025-12-31', display_account='all')
        self.assertEqual(lines[revenue]['initial_balance'], 0.0)
        self.assertEqual(lines[receivable]['initial_balance'], 100.0)
        self.assertEqual(lines['']['initial_balance'], -100.0)

        # without a start date, no initial balance: the period is the whole history
        lines = self._trial_balance(accounts, date_to='2025-12-31', display_account='all')
        self.assertEqual(lines[receivable]['initial_balance'], 0.0)
        self.assertEqual(lines[receivable]['balance'], 170.0)
        self.assertNotIn('', lines)

    def test_trial_balance_adds_up_to_zero(self):
        """ Every column of the whole chart adds up, the income of the closed years included. """
        for amount, day in ((100.0, '2024-06-01'), (40.0, '2025-03-01'), (30.0, '2025-08-01')):
            self.init_invoice('out_invoice', partner=self.partner_a, amounts=[amount], taxes=[],
                              invoice_date=day, post=True)
        accounts = self.env['account.account'].search([])
        lines = self._trial_balance_lines(accounts, date_from='2025-07-01', date_to='2025-12-31',
                                          display_account='all')
        self.assertAlmostEqual(sum(line['initial_balance'] for line in lines), 0.0)
        self.assertAlmostEqual(sum(line['balance'] for line in lines), 0.0)
        self.assertAlmostEqual(sum(line['debit'] for line in lines), sum(line['credit'] for line in lines))

    def test_trial_balance_undistributed_line_only_when_relevant(self):
        """ No line for balance sheet accounts alone, whatever the filter. """
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2024-06-01', post=True)
        receivable = self.company_data['default_account_receivable']
        revenue = self.company_data['default_account_revenue']
        form = {'date_from': '2025-07-01', 'date_to': '2025-12-31'}
        self.assertNotIn('', self._trial_balance(receivable, display_account='all', **form))
        self.assertIn('', self._trial_balance(revenue, display_account='not_zero', **form))
        self.assertIn('', self._trial_balance(revenue, display_account='movement', **form))

    def test_trial_balance_adds_up_with_every_filter(self):
        """ With a start date no filter leaves an account out: not one without movements but with a balance, nor
        one with movements that ends at zero. """
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                                    invoice_date='2025-03-01', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[40.0], taxes=[],
                          invoice_date='2024-03-01', post=True)
        receivable = invoice.line_ids.filtered(lambda line: line.account_type == 'asset_receivable')
        bank = self.company_data['default_journal_bank'].default_account_id
        paid = self.env['account.move'].create({
            'move_type': 'entry', 'date': '2025-08-01', 'line_ids': [
                fields.Command.create({'account_id': bank.id, 'debit': 140.0, 'name': 'paid'}),
                fields.Command.create({'account_id': receivable.account_id.id, 'credit': 140.0, 'name': 'paid',
                                       'partner_id': self.partner_a.id}),
            ]})
        paid.action_post()
        field = 'company_ids' if 'company_ids' in self.env['account.account']._fields else 'company_id'
        accounts = self.env['account.account'].search([]).filtered(lambda account: self.env.company in account[field])
        form = {'date_from': '2025-07-01', 'date_to': '2025-12-31'}
        for display_account in ('all', 'movement', 'not_zero'):
            lines = self._trial_balance_lines(accounts, display_account=display_account, **form)
            self.assertAlmostEqual(sum(line['initial_balance'] for line in lines), 0.0, msg=display_account)
            self.assertAlmostEqual(sum(line['balance'] for line in lines), 0.0, msg=display_account)
            self.assertAlmostEqual(sum(line['debit'] for line in lines), sum(line['credit'] for line in lines),
                                   msg=display_account)
            self.assertEqual(sum(line['credit'] for line in lines), 140.0, msg=display_account)
