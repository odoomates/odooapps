from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAnnualReport(AccountTestInvoicingCommon):
    """ The year-end pack: one PDF holding the statements that are otherwise printed apart. """

    def _report(self, **form):
        """ :return: (wizard, report values) for the pack

        Built through check_report(), the same path the Print button takes. Assembling
        the form by hand here once meant the tests quietly stopped seeing new options
        the report had grown.
        """
        wizard = self.env['account.annual.report'].with_context(
            active_model='account.annual.report').create(form)
        action = wizard.check_report()
        values = self.env['report.accounting_pdf_reports.report_annual']._get_report_values(
            wizard.ids, action['data'])
        return wizard, values

    def _names(self, values):
        return [statement['name'] for statement in values['statements']]

    def _cash_received(self, amount, date):
        """ Money actually arriving in the bank account on a date.

        Not a registered payment: in Odoo 20 a payment settles into Outstanding
        Receipts and only reaches the cash account once a bank statement is
        reconciled, so it would move no cash at all.
        """
        bank = self.company_data['default_journal_bank'].default_account_id
        revenue = self.company_data['default_account_revenue']
        move = self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_bank'].id,
            'date': date,
            'line_ids': [
                (0, 0, {'name': 'receipt', 'account_id': bank.id, 'balance': amount}),
                (0, 0, {'name': 'receipt', 'account_id': revenue.id, 'balance': -amount}),
            ],
        })
        move.action_post()
        return move

    # ------------------------------------------------------------------
    # the period
    # ------------------------------------------------------------------

    def test_the_wizard_opens_on_the_current_fiscal_year(self):
        """ It is an annual report: the year should already be filled in. """
        wizard = self.env['account.annual.report'].create({})
        year = self.env.company.compute_fiscalyear_dates(fields.Date.context_today(wizard))

        self.assertEqual(wizard.date_from, year['date_from'])
        self.assertEqual(wizard.date_to, year['date_to'])

    def test_the_dates_have_to_run_forwards(self):
        wizard = self.env['account.annual.report'].create({
            'date_from': '2026-12-31', 'date_to': '2026-01-01',
        })
        with self.assertRaises(UserError):
            wizard._print_report({'form': {}})

    def test_an_empty_pack_is_refused(self):
        """ A report with every section switched off would print a cover page and nothing else. """
        wizard = self.env['account.annual.report'].create({
            'include_balance_sheet': False,
            'include_profit_and_loss': False,
            'include_cash_flow': False,
        })
        with self.assertRaises(UserError):
            wizard._print_report({'form': {}})

    # ------------------------------------------------------------------
    # the contents
    # ------------------------------------------------------------------

    def test_the_pack_carries_both_statements(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)
        __, values = self._report(date_from='2026-01-01', date_to='2026-12-31')

        self.assertEqual(self._names(values), ['Balance Sheet', 'Profit and Loss'])
        for statement in values['statements']:
            self.assertTrue(statement['lines'], "%s printed no lines" % statement['name'])

    def test_the_sections_are_the_ones_that_were_asked_for(self):
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_profit_and_loss=False)
        self.assertEqual(self._names(values), ['Balance Sheet'])

        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_balance_sheet=False)
        self.assertEqual(self._names(values), ['Profit and Loss'])

    def test_the_cash_flow_is_left_out_unless_it_is_asked_for(self):
        __, values = self._report(date_from='2026-01-01', date_to='2026-12-31')
        self.assertIsNone(values['cash_flow'])

        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_cash_flow=True)
        self.assertIsNotNone(values['cash_flow'])
        self.assertIn('sections', values['cash_flow'])

    # ------------------------------------------------------------------
    # the numbers
    # ------------------------------------------------------------------

    def test_the_figures_are_the_ones_the_standalone_reports_print(self):
        """ The pack delegates to the financial report engine rather than recomputing.

        This is what stops the annual report and the Balance Sheet ever disagreeing,
        so it is asserted directly: same period, same numbers, line for line.
        """
        self.init_invoice('out_invoice', amounts=[1234.0], invoice_date='2026-03-01', taxes=[], post=True)
        self.init_invoice('in_invoice', amounts=[567.0], invoice_date='2026-04-01', taxes=[], post=True)

        wizard, values = self._report(date_from='2026-01-01', date_to='2026-12-31')

        financial = self.env['report.accounting_pdf_reports.report_financial']
        for xmlid, name in (('account_financial_report_balancesheet0', 'Balance Sheet'),
                            ('account_financial_report_profitandloss0', 'Profit and Loss')):
            report = self.env.ref('accounting_pdf_reports.%s' % xmlid)
            standalone = financial.get_account_lines({
                'account_report_id': (report.id, report.name),
                'used_context': dict(wizard._build_contexts({'form': wizard.read(
                    ['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]})),
                'enable_filter': False,
                'debit_credit': False,
            })
            section = next(s for s in values['statements'] if s['name'] == name)
            self.assertEqual(
                [(line['name'], line['balance']) for line in section['lines']],
                [(line['name'], line['balance']) for line in standalone],
                "the %s in the pack differs from the standalone report" % name)

    # ------------------------------------------------------------------
    # the cover and the contents
    # ------------------------------------------------------------------

    def test_the_contents_name_every_section_in_order(self):
        # the statements only: the extra pages have tests of their own
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_cash_flow=True,
            include_key_figures=False)

        self.assertEqual([entry['name'] for entry in values['contents']],
                         ['Balance Sheet', 'Profit and Loss', 'Cash Flow Statement'])

    def test_the_contents_point_at_the_page_each_section_starts_on(self):
        """The cover is page 1 and the contents page 2, so the first statement is
        page 3, and each one after it starts where the previous one ended."""
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_cash_flow=True,
            include_key_figures=False)

        pages = {entry['name']: entry['page'] for entry in values['contents']}
        self.assertEqual(pages['Balance Sheet'], 3)

        balance_sheet = next(s for s in values['statements'] if s['name'] == 'Balance Sheet')
        self.assertEqual(pages['Profit and Loss'], 3 + len(balance_sheet['pages']))

        profit_and_loss = next(s for s in values['statements'] if s['name'] == 'Profit and Loss')
        self.assertEqual(pages['Cash Flow Statement'],
                         pages['Profit and Loss'] + len(profit_and_loss['pages']))

    def test_a_long_statement_is_cut_into_pages(self):
        report = self.env['report.accounting_pdf_reports.report_annual']
        lines = [{'name': 'line %s' % i, 'balance': 0.0, 'level': 1} for i in range(70)]

        pages = report._paginate(lines)

        self.assertEqual(len(pages), 3, "70 rows should not be printed on one page")
        self.assertEqual(sum(len(page) for page in pages), 70, "no row may be dropped")

    def test_pagination_skips_the_rows_the_template_hides(self):
        """Level 0 lines are not printed, so they must not be counted either - or the
        page numbers in the contents drift away from the pages themselves."""
        report = self.env['report.accounting_pdf_reports.report_annual']
        lines = [{'name': 'hidden', 'balance': 0.0, 'level': 0} for _i in range(40)]
        lines += [{'name': 'shown', 'balance': 0.0, 'level': 1}]

        pages = report._paginate(lines)

        self.assertEqual(len(pages), 1)
        self.assertEqual(len(pages[0]), 1)

    # ------------------------------------------------------------------
    # last year's column
    # ------------------------------------------------------------------

    def test_the_comparison_covers_the_same_span_a_year_earlier(self):
        wizard = self.env['account.annual.report'].create({
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })
        comparison = wizard._comparison({'form': {'used_context': {}}})

        self.assertEqual(str(comparison['date_from_cmp']), '2025-01-01')
        self.assertEqual(str(comparison['date_to_cmp']), '2025-12-31')

    def test_the_comparison_keeps_the_journals_and_the_target_moves(self):
        """Only the dates may differ, or the two columns are not comparable."""
        wizard = self.env['account.annual.report'].create({
            'date_from': '2026-01-01', 'date_to': '2026-12-31', 'target_move': 'all',
        })
        data = {'form': wizard.read(
            ['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]}
        data['form']['used_context'] = wizard._build_contexts(data)

        comparison = wizard._comparison(data)['comparison_context']

        self.assertEqual(comparison['state'], data['form']['used_context']['state'])
        self.assertEqual(comparison['journal_ids'], data['form']['used_context']['journal_ids'])
        self.assertEqual(comparison['company_id'], data['form']['used_context']['company_id'])

    def test_last_years_figures_are_last_years(self):
        """The point of the column: it must hold the earlier year, not repeat this one."""
        self.init_invoice('out_invoice', amounts=[400.0], invoice_date='2025-06-01', taxes=[], post=True)
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)

        __, values = self._report(date_from='2026-01-01', date_to='2026-12-31')

        profit_and_loss = next(s for s in values['statements'] if s['name'] == 'Profit and Loss')
        income = next(line for line in profit_and_loss['lines'] if line['name'] == 'Income')
        self.assertEqual(income['balance'], 1000.0)
        self.assertEqual(income['balance_cmp'], 400.0)

    def test_without_the_comparison_there_is_no_second_column(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', compare_previous_year=False)

        for statement in values['statements']:
            for line in statement['lines']:
                self.assertNotIn('balance_cmp', line)

    def test_the_comparison_reaches_the_printed_page(self):
        self.init_invoice('out_invoice', amounts=[400.0], invoice_date='2025-06-01', taxes=[], post=True)
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)
        wizard = self.env['account.annual.report'].with_context(
            active_model='account.annual.report').create({
                'date_from': '2026-01-01', 'date_to': '2026-12-31'})
        action = wizard.check_report()

        html, __ = self.env['ir.actions.report']._render_qweb_html(
            'accounting_pdf_reports.report_annual', wizard.ids, data=action['data'])
        body = html.decode() if isinstance(html, bytes) else str(html)

        self.assertIn('400.00', body, "last year's figure is missing from the page")
        self.assertIn('With comparatives for', body)

    def test_the_cash_flow_is_compared_too(self):
        """The engine has no comparison of its own, so it is run twice and merged."""
        self._cash_received(400.0, '2025-05-10')
        self._cash_received(1000.0, '2026-05-10')

        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_cash_flow=True)
        cash_flow = values['cash_flow']

        self.assertEqual(cash_flow['net_change'], 1000.0)
        self.assertEqual(cash_flow['net_change_cmp'], 400.0)
        for key in ('opening', 'closing'):
            self.assertIn('%s_cmp' % key, cash_flow)
        for section in cash_flow['sections']:
            self.assertIn('total_cmp', section)
            for line in section['lines']:
                self.assertIn('amount_cmp', line)

    def test_a_line_that_only_existed_last_year_still_shows(self):
        """Zero lines are dropped by the engine, so a row present only in the earlier
        period would otherwise disappear along with its figure."""
        report = self.env['report.accounting_pdf_reports.report_annual']
        current = {
            'sections': [{'activity': 'operating', 'name': 'Operating', 'total': 10.0,
                          'lines': [{'key': 'receivable', 'name': 'From customers', 'amount': 10.0}]}],
            'opening': 0.0, 'net_change': 10.0, 'closing': 10.0,
        }
        previous = {
            'sections': [{'activity': 'operating', 'name': 'Operating', 'total': 7.0,
                          'lines': [{'key': 'payable', 'name': 'To suppliers', 'amount': 7.0}]}],
            'opening': 0.0, 'net_change': 7.0, 'closing': 7.0,
        }

        merged = report._merge_cash_flow(current, previous)

        lines = {line['key']: line for line in merged['sections'][0]['lines']}
        self.assertEqual(sorted(lines), ['payable', 'receivable'])
        self.assertEqual(lines['receivable']['amount_cmp'], 0.0)
        self.assertEqual(lines['payable']['amount'], 0.0)
        self.assertEqual(lines['payable']['amount_cmp'], 7.0)

    # ------------------------------------------------------------------
    # variance, key figures, notes, approval
    # ------------------------------------------------------------------

    def test_the_variance_is_the_movement_between_the_columns(self):
        self.init_invoice('out_invoice', amounts=[400.0], invoice_date='2025-06-01', taxes=[], post=True)
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)

        __, values = self._report(date_from='2026-01-01', date_to='2026-12-31')

        profit_and_loss = next(s for s in values['statements'] if s['name'] == 'Profit and Loss')
        income = next(line for line in profit_and_loss['lines'] if line['name'] == 'Income')
        self.assertEqual(income['variance'], 600.0)
        self.assertAlmostEqual(income['variance_pct'], 150.0)

    def test_a_movement_from_nothing_has_no_percentage(self):
        """Dividing by a prior period of zero would be a crash or a meaningless number."""
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)

        __, values = self._report(date_from='2026-01-01', date_to='2026-12-31')

        profit_and_loss = next(s for s in values['statements'] if s['name'] == 'Profit and Loss')
        income = next(line for line in profit_and_loss['lines'] if line['name'] == 'Income')
        self.assertEqual(income['variance'], 1000.0)
        self.assertIs(income['variance_pct'], False)

    def test_no_variance_without_a_comparison(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', compare_previous_year=False)

        for statement in values['statements']:
            for line in statement['lines']:
                self.assertNotIn('variance', line)

    def test_the_key_figures_agree_with_the_statements(self):
        """They come from the same report roots, so they must not tell a different story."""
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)

        __, values = self._report(date_from='2026-01-01', date_to='2026-12-31')

        figures = {figure['label']: figure['amount'] for figure in values['key_figures']}
        self.assertEqual(sorted(figures), ['Expenses', 'Result for the period', 'Revenue', 'Total assets'])

        profit_and_loss = next(s for s in values['statements'] if s['name'] == 'Profit and Loss')
        income = next(line for line in profit_and_loss['lines'] if line['name'] == 'Income')
        self.assertEqual(figures['Revenue'], income['balance'])

    def test_the_key_figures_carry_last_year_too(self):
        self.init_invoice('out_invoice', amounts=[400.0], invoice_date='2025-06-01', taxes=[], post=True)
        __, values = self._report(date_from='2026-01-01', date_to='2026-12-31')

        revenue = next(f for f in values['key_figures'] if f['label'] == 'Revenue')
        self.assertEqual(revenue['amount_cmp'], 400.0)

    def test_the_extras_are_optional(self):
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31',
            include_key_figures=False, include_signatures=False)

        self.assertEqual(values['key_figures'], [])
        self.assertEqual(values['notes'], '')
        self.assertNotIn('Key Figures', [entry['name'] for entry in values['contents']])

    def test_every_extra_page_is_counted_in_the_contents(self):
        """Inserting pages is what breaks a table of contents, so this pins the order
        and the arithmetic with all of them switched on."""
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_cash_flow=True,
            include_key_figures=True, include_signatures=True, notes='Something worth saying.')

        entries = values['contents']
        self.assertEqual([entry['name'] for entry in entries], [
            'Key Figures', 'Balance Sheet', 'Profit and Loss', 'Cash Flow Statement',
            'Notes to the Financial Statements', 'Approval'])

        # the cover and the contents take pages 1 and 2, then nothing may overlap
        self.assertEqual(entries[0]['page'], 3)
        for earlier, later in zip(entries, entries[1:]):
            self.assertGreater(later['page'], earlier['page'])

    def test_the_extra_pages_reach_the_paper(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-06-01', taxes=[], post=True)
        wizard = self.env['account.annual.report'].with_context(
            active_model='account.annual.report').create({
                'date_from': '2026-01-01', 'date_to': '2026-12-31',
                'include_signatures': True, 'notes': 'Depreciation is straight line.'})
        action = wizard.check_report()

        html, __ = self.env['ir.actions.report']._render_qweb_html(
            'accounting_pdf_reports.report_annual', wizard.ids, data=action['data'])
        body = html.decode() if isinstance(html, bytes) else str(html)

        self.assertIn('Key Figures', body)
        self.assertIn('Result for the period', body)
        self.assertIn('Depreciation is straight line.', body)
        self.assertIn('Prepared by', body)
        self.assertIn('Variance', body)

    # ------------------------------------------------------------------
    # printing
    # ------------------------------------------------------------------

    def test_printing_returns_a_report_action(self):
        wizard = self.env['account.annual.report'].with_context(
            active_model='account.annual.report').create({})
        action = wizard.check_report()

        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'accounting_pdf_reports.report_annual')
        self.assertTrue(action['data']['form']['include_balance_sheet'])

    def test_the_template_renders(self):
        """Render the QWeb end to end.

        The other tests stop at the values the report hands the template, so a typo in
        report_annual.xml would pass every one of them and only fail when someone
        pressed Print.
        """
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2026-05-01', taxes=[], post=True)
        wizard = self.env['account.annual.report'].with_context(
            active_model='account.annual.report').create({
                'date_from': '2026-01-01', 'date_to': '2026-12-31', 'include_cash_flow': True,
            })
        action = wizard.check_report()

        html, report_type = self.env['ir.actions.report']._render_qweb_html(
            'accounting_pdf_reports.report_annual', wizard.ids, data=action['data'])

        self.assertEqual(report_type, 'html')
        body = html.decode() if isinstance(html, bytes) else str(html)
        self.assertIn('Annual Report', body)

        # Assert on the rows, not on the headings: the headings also appear in the
        # contents list on the cover, so a section that rendered nothing at all would
        # still leave its name in the page and pass.
        __, values = self._report(
            date_from='2026-01-01', date_to='2026-12-31', include_cash_flow=True)
        for statement in values['statements']:
            for line in statement['lines']:
                self.assertIn(line['name'], body,
                              "%s did not print its lines" % statement['name'])
        self.assertIn('Cash and cash equivalents at the end of the period', body)

        # the cover carries the company, and the contents page its entries
        self.assertIn(self.env.company.name, body)
        self.assertIn('Contents', body)
        for entry in values['contents']:
            self.assertIn(entry['name'], body)

    def test_the_report_refuses_an_empty_form(self):
        with self.assertRaises(UserError):
            self.env['report.accounting_pdf_reports.report_annual']._get_report_values([], {})
