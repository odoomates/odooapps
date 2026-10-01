from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBalanceSheet(AccountTestInvoicingCommon):
    """ What the Balance Sheet of this module reports.

    The tree of 19.0 is:

        Balance Sheet
        |-- Assets
        `-- Liability                     (a sum)
            |-- Liability                 (payable, credit card, equity, liabilities, unaffected)
            `-- Profit (Loss) to report

    so the equity is counted among the liabilities and two nodes carry the same name.
    Both are deliberate here: separating them changes a record the customer may have
    adapted, and that is a migration rather than a fix. The tests below say what the
    report does today, whichever way that question is answered later.
    """

    def _balance_sheet(self, date_to):
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        balances = self.env['report.accounting_pdf_reports.report_financial'].with_context(
            date_from=False, date_to=date_to, state='posted', strict_range=False,
            company_id=self.env.company.id,
        )._compute_report_balance(report.children_ids)
        return {line.name: balances[line.id]['balance'] for line in report.children_ids}

    def _lines(self, date_to=False):
        """ :return: the report lines as they are printed, the sign of each one applied """
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        return self.env['report.accounting_pdf_reports.report_financial'].get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': {'date_from': False, 'date_to': date_to, 'state': 'posted',
                             'strict_range': False, 'company_id': self.env.company.id},
            'enable_filter': False,
            'debit_credit': False,
        })

    def _entry(self, date, debit_account, credit_account, amount):
        return self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': date,
            'line_ids': [
                (0, 0, {'name': 'entry', 'balance': amount, 'account_id': debit_account.id}),
                (0, 0, {'name': 'entry', 'balance': -amount, 'account_id': credit_account.id}),
            ],
        }).action_post()

    # -------------------------------------------------------------------------
    # It balances
    # -------------------------------------------------------------------------

    def test_balance_sheet_balances_with_current_year_earnings_postings(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-06-01', taxes=[], post=True)
        retained_earnings = self.env['account.account'].create({
            'code': 'RETEARN', 'name': 'Retained Earnings', 'account_type': 'equity',
        })
        # e.g. the transfer of the earnings of 2025, or an opening balance difference
        self._entry('2026-01-01', self.env.company.get_unaffected_earnings_account(),
                    retained_earnings, 1000.0)

        for date_to in ('2025-12-31', '2026-12-31'):
            with self.subTest(date_to=date_to):
                lines = self._balance_sheet(date_to)
                self.assertAlmostEqual(sum(lines.values()), 0.0)
                self.assertAlmostEqual(lines['Assets'], 1000.0)

    def test_a_credit_card_balances(self):
        """ A credit card is money owed: without it on the other side the report does not balance. """
        credit_card = self.env['account.account'].create({
            'code': 'CCARD', 'name': 'Company Card', 'account_type': 'liability_credit_card',
        })
        expense = self.env['account.account'].create({
            'code': 'CCEXP', 'name': 'Card Expense', 'account_type': 'expense',
        })
        self._entry('2025-06-01', expense, credit_card, 250.0)

        self.assertAlmostEqual(sum(self._balance_sheet('2025-12-31').values()), 0.0)

    def test_prepayments_are_assets(self):
        prepayments = self.env['account.account'].create({
            'code': 'PREPAID', 'name': 'Prepaid Rent', 'account_type': 'asset_prepayments',
        })
        self._entry('2025-06-01', prepayments, self.company_data['default_account_payable'], 600.0)

        lines = self._balance_sheet('2025-12-31')
        self.assertAlmostEqual(lines['Assets'], 600.0)
        self.assertAlmostEqual(sum(lines.values()), 0.0)

    # -------------------------------------------------------------------------
    # How it reads
    # -------------------------------------------------------------------------

    def test_the_two_sides_cancel_each_other(self):
        """ 19.0 prints the liability side negative and the assets positive, so the two add
        up to nothing rather than facing each other as two positive columns.

        20.0 prints both sides positive. Changing the sign here changes a report people read
        every day, so it is recorded rather than corrected.
        """
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-06-01', taxes=[], post=True)

        printed = [(line['name'], line['level'], line['balance'])
                   for line in self._lines('2025-12-31') if line['type'] == 'report']
        sides = {name: balance for name, level, balance in printed if level == 1}

        self.assertAlmostEqual(sides['Assets'], 1000.0)
        self.assertAlmostEqual(sides['Liability'], -1000.0)
        self.assertAlmostEqual(sides['Assets'] + sides['Liability'], 0.0)
        self.assertAlmostEqual(dict(((n, l), b) for n, l, b in printed)[('Profit (Loss) to report', 2)],
                               -1000.0, msg='the profit of the period sits on the side of the owners')

    def test_the_lines_carry_their_level(self):
        """ The sections are indented by their depth in the report.

        The order they come in is deliberately not asserted: only one record of the tree of
        19.0 carries a sequence, so the sections come back in whatever order the database
        returns them and Assets and Liability change places between runs. That is recorded
        as a defect rather than tested for.
        """
        levels = sorted((line['name'], line['level'])
                        for line in self._lines() if line['type'] == 'report')

        self.assertEqual(levels, sorted([
            ('Balance Sheet', 0),
            ('Assets', 1),
            ('Liability', 1),
            ('Liability', 2),
            ('Profit (Loss) to report', 2),
        ]))

        self.env.ref('accounting_pdf_reports.account_financial_report_liability0').style_overwrite = '1'
        promoted = [line['level'] for line in self._lines()
                    if line['name'] == 'Liability' and line['type'] == 'report']
        self.assertEqual(promoted, [1, 1], 'a style chosen on the line wins over its depth')

    def test_the_sections_come_back_in_no_particular_order(self):
        """ 19.0 sets a sequence on one record of the tree, so the Balance Sheet can print
        Assets above Liability on one run and below it on the next. 20.0 numbers every node.

        Numbering them here would change a record the customer may have adapted, so the
        defect is recorded and left for the decision it deserves.
        """
        root = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')

        self.assertTrue(all(child.sequence == 0 for child in root.children_ids),
                        'nothing orders the two sides of the balance sheet')

    # -------------------------------------------------------------------------
    # What the tree of 19.0 counts, and where
    # -------------------------------------------------------------------------

    def test_nothing_is_counted_on_both_sides(self):
        """ An account type on both sides would be added twice and the report would still
        balance, which is why it is worth a test of its own. """
        assets = self.env.ref('accounting_pdf_reports.account_financial_report_assets0')
        liabilities = self.env.ref('accounting_pdf_reports.account_financial_report_liability0')

        overlap = set(assets.account_type_ids.mapped('type')) & set(liabilities.account_type_ids.mapped('type'))

        self.assertFalse(overlap, 'an account type belongs to one side of the balance sheet')

    def test_the_equity_is_reported_with_the_liabilities(self):
        """ 19.0 keeps the equity inside the Liability node. This test records that, so that
        the day it is separated the change is a decision and not a surprise. """
        liabilities = self.env.ref('accounting_pdf_reports.account_financial_report_liability0')

        types = set(liabilities.account_type_ids.mapped('type'))

        self.assertIn('equity', types)
        self.assertIn('equity_unaffected', types)
        self.assertIn('liability_credit_card', types)

    def test_the_sections_keep_their_order(self):
        """ The sections without a sequence print in the order they were created (Assets before the
        liabilities, Income before Expense), not in the order the database happens to return them. """
        for xmlid in ('accounting_pdf_reports.account_financial_report_balancesheet0',
                      'accounting_pdf_reports.account_financial_report_profitandloss0'):
            report = self.env.ref(xmlid)
            sections = report.children_ids.sorted(lambda section: (section.sequence, section.id))
            # an update writes the row anew at the end of the table, where a scan finds it last
            # (the ORM skips a write of the same value: the update is made in SQL)
            self.env.cr.execute("UPDATE account_financial_report SET name = name WHERE id = %s", [sections[0].id])
            printed = report._get_children_by_order().filtered(lambda line: line.parent_id == report)
            # the ids, in order: two recordsets compare equal whatever their order
            self.assertEqual(printed.ids, sections.ids, xmlid)
