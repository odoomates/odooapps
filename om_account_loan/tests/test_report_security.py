from datetime import date

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import LoanCommon


@tagged('post_install', '-at_install')
class TestLoanReport(LoanCommon):

    def _report(self, day, loans=None):
        report = self.env['account.loan.report'].create({
            'date': day, **({'loan_ids': [Command.set(loans.ids)]} if loans else {})})
        report._compute_lines()
        return report

    def test_report_values(self):
        loan = self._create_loan(payment_count=24)
        self._draw(loan)
        lines = self._lines(loan)
        for line in lines[:3]:
            self._pay(line)
        line = self._report(date(2025, 4, 15), loan).line_ids
        outstanding = round(100000.0 - sum(lines[:3].mapped('principal')), 2)
        within = round(sum(lines[3:15].mapped('principal')), 2)
        self.assertEqual(line.loan_id, loan)
        self.assertEqual(line.partner_id, self.lender)
        self.assertEqual(line.outstanding, outstanding)
        self.assertEqual(line.accrued_interest, round(outstanding * 0.06 / 12 * 14 / 30, 2))
        self.assertEqual(line.next_date, date(2025, 5, 1))
        self.assertEqual(line.next_amount, lines[3].amount)
        self.assertAlmostEqual(line.due_within, within, places=2)
        self.assertAlmostEqual(line.due_after, outstanding - within, places=2)
        self.assertEqual(line.outstanding_company, outstanding)
        self.assertEqual(line.rate, 6.0)
        # before the payment of an instalment due, it stays the next one
        line = self._report(date(2025, 5, 10), loan).line_ids
        self.assertEqual(line.next_date, date(2025, 5, 1))
        self.assertEqual(line.accrued_interest, round(lines[3].closing_balance * 0.06 / 12 * 9 / 31, 2))
        # nothing drawn before the start
        self.assertFalse(self._report(date(2024, 12, 31), loan).line_ids.outstanding)

    def test_report_every_loan(self):
        loans = self._create_loan() | self._create_loan(principal=50000.0)
        self._create_loan(confirm=False)
        for loan in loans:
            self._draw(loan)
        report = self._report(date(2025, 1, 15))
        self.assertEqual(report.line_ids.loan_id, loans)
        action = report.action_view()
        self.assertEqual(action['res_model'], 'account.loan.report.line')
        self.assertEqual(self.env['account.loan.report.line'].search(action['domain']), report.line_ids)

    def test_pdf_reports(self):
        loan = self._create_loan()
        self._draw(loan)
        self._pay(self._lines(loan)[0])
        html = self.env['ir.actions.report']._render_qweb_html('om_account_loan.report_loan', loan.ids)[0]
        self.assertIn(loan.name, str(html))
        self.assertIn('8,606.64', str(html))
        report = self._report(date(2025, 2, 15), loan)
        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_loan.report_loan_position', report.ids)[0]
        self.assertIn('91,893.36', str(html))


@tagged('post_install', '-at_install')
class TestLoanSecurity(LoanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.manager = new_test_user(
            cls.env, login='loan_manager', groups='account.group_account_manager,account.group_account_user',
            company_id=company.id)
        cls.accountant = new_test_user(
            cls.env, login='loan_accountant', groups='account.group_account_user', company_id=company.id)
        cls.invoicing = new_test_user(
            cls.env, login='loan_invoicing', groups='account.group_account_invoice', company_id=company.id)

    def test_manager_runs_loans(self):
        loan = self._create_loan(confirm=False).with_user(self.manager)
        loan.action_confirm()
        self.env['account.loan.drawdown'].with_user(self.manager).create(
            {'loan_id': loan.id, 'date': loan.date_start}).action_confirm()
        self.env['account.loan.pay'].with_user(self.manager).create(
            {'line_id': loan.line_ids.sorted('sequence')[0].id}).action_confirm()
        self.assertEqual(loan.line_ids.sorted('sequence')[0].state, 'posted')

    def test_accountant_reads(self):
        loan = self._create_loan()
        self._draw(loan)
        loan = loan.with_user(self.accountant)
        self.assertEqual(loan.outstanding_amount, 100000.0)
        self.assertTrue(loan.line_ids.mapped('amount'))
        self.assertTrue(loan.move_ids)
        with self.assertRaises(AccessError):
            loan.lender_ref = 'X'
        with self.assertRaises(AccessError):
            self.env['account.loan'].with_user(self.accountant).create({
                'partner_id': self.lender.id, 'principal': 1000.0})
        with self.assertRaises(AccessError):
            self.env['account.loan.drawdown'].with_user(self.accountant).create({'loan_id': loan.id})
        report = self.env['account.loan.report'].with_user(self.accountant).create({'date': date(2025, 1, 31)})
        report._compute_lines()
        self.assertEqual(report.line_ids.loan_id, loan)

    def test_invoicing_user_no_access(self):
        loan = self._create_loan()
        move = self._draw(loan).move_id
        with self.assertRaises(AccessError):
            loan.with_user(self.invoicing).read(['name'])
        with self.assertRaises(AccessError):
            self.env['account.loan.line'].with_user(self.invoicing).search([])
        # the entries stay readable, without their loan
        self.assertEqual(move.with_user(self.invoicing).read(['name'])[0]['name'], move.name)

    def test_multi_company(self):
        company_2 = self.setup_other_company(name='Loan Company 2')['company']
        Account = self.env['account.account'].with_company(company_2)
        accounts = {
            fname: Account.create({'code': code, 'name': fname, 'account_type': account_type})
            for fname, code, account_type in (
                ('account_long_term_id', '171901', 'liability_non_current'),
                ('account_short_term_id', '161901', 'liability_current'),
                ('account_interest_id', '661901', 'expense'))
        }
        journal = self.env['account.journal'].with_company(company_2)
        loan_2 = self.env['account.loan'].with_company(company_2).create({
            'partner_id': self.lender.id,
            'principal': 5000.0,
            'company_id': company_2.id,
            'date_start': date(2025, 1, 1),
            **{fname: account.id for fname, account in accounts.items()},
            'journal_id': journal.search([('company_id', '=', company_2.id), ('type', '=', 'general')], limit=1).id,
            'bank_journal_id': journal.search([('company_id', '=', company_2.id), ('type', '=', 'bank')], limit=1).id,
        })
        loan_2.action_confirm()
        loan_1 = self._create_loan()
        self.assertEqual(
            self.env['account.loan'].with_user(self.manager).search([('id', 'in', (loan_1 | loan_2).ids)]), loan_1)
        self.assertFalse(
            self.env['account.loan.line'].with_user(self.manager).search([('loan_id', '=', loan_2.id)]))
        with self.assertRaises(AccessError):
            loan_2.with_user(self.manager).read(['name'])
        self.manager.company_ids |= company_2
        both = self.env['account.loan'].with_user(self.manager).with_context(
            allowed_company_ids=(self.env.company | company_2).ids)
        self.assertEqual(both.search([('id', 'in', (loan_1 | loan_2).ids)]), loan_1 | loan_2)
