from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBranchReports(AccountTestInvoicingCommon):
    """ A branch posts its entries in its own company: the reports of the parent consolidate them. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['res.company'].create({
            'name': 'Branch of %s' % cls.env.company.name,
            'parent_id': cls.env.company.id,
        })
        cls.env.user.company_ids |= cls.branch
        cls.branch_journal = cls.env['account.journal'].create({
            'name': 'Branch Miscellaneous', 'code': 'BMSC', 'type': 'general',
            'company_id': cls.branch.id,
        })
        # the parent and its branch both enabled, as the company switcher leaves them when the
        # parent is selected. Record rules read allowed_company_ids, so the state is set here
        # rather than left to the default of the test framework.
        cls.env_tree = cls.env(context=dict(
            cls.env.context, allowed_company_ids=[cls.env.company.id, cls.branch.id]))

    def _post_entry(self, company, journal, amount):
        move = self.env['account.move'].with_company(company).create({
            'journal_id': journal.id,
            'date': '2025-06-01',
            'line_ids': [
                (0, 0, {'name': 'debit', 'balance': amount,
                        'account_id': self.company_data['default_account_receivable'].id}),
                (0, 0, {'name': 'credit', 'balance': -amount,
                        'account_id': self.company_data['default_account_revenue'].id}),
            ],
        })
        move.action_post()
        return move

    def _balance_sheet(self, company):
        report = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        balances = self.env_tree['report.accounting_pdf_reports.report_financial'].with_context(
            date_from=False, date_to='2025-12-31', state='posted', strict_range=False,
            company_id=company.id,
        )._compute_report_balance(report.children_ids)
        return {line.name: balances[line.id]['balance'] for line in report.children_ids}

    def test_parent_balance_sheet_consolidates_the_branch(self):
        self._post_entry(self.env.company, self.company_data['default_journal_misc'], 100.0)
        self._post_entry(self.branch, self.branch_journal, 250.0)

        # the parent carries its own entries and the ones of the branch, the branch only its own
        self.assertAlmostEqual(self._balance_sheet(self.env.company)['Assets'], 350.0)
        self.assertAlmostEqual(self._balance_sheet(self.branch)['Assets'], 250.0)

    def test_journal_selector_offers_the_branch_journals(self):
        wizard = self.env_tree['account.aged.trial.balance'].create({'date_from': '2025-12-31'})
        # the default is every journal the report may read, those of the branches included
        self.assertIn(self.branch_journal, wizard.journal_ids)
