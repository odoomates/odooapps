import io
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.om_account_loan.wizard.account_loan_import import parse_amount

from .common import LoanCommon

SCHEDULE = """Date,Principal,Interest
2025-02-01,30000.00,500.00
2025-03-01,30000.00,350.00
2025-04-01,40000.00,200.00
"""


@tagged('post_install', '-at_install')
class TestImportSchedule(LoanCommon):

    def _imported_loan(self, **vals):
        return self._create_loan(confirm=False, schedule_method='imported', **vals)

    def test_parse_amount(self):
        self.assertEqual(parse_amount('1,234.56'), 1234.56)
        self.assertEqual(parse_amount('1.234,56'), 1234.56)
        self.assertEqual(parse_amount('1234,5'), 1234.5)
        self.assertEqual(parse_amount('1,234'), 1234.0)
        self.assertEqual(parse_amount('1 234,56'), 1234.56)
        self.assertEqual(parse_amount(''), 0.0)
        self.assertEqual(parse_amount(12.5), 12.5)
        with self.assertRaises(ValueError):
            parse_amount('abc')

    def test_import_csv(self):
        """ The lines of the file replace the schedule; the loan then runs on them. """
        loan = self._imported_loan()
        with self.assertRaises(UserError):
            loan.action_confirm()
        self._import(loan, SCHEDULE)
        lines = self._lines(loan)
        self.assertEqual(lines.mapped('date'), [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)])
        self.assertEqual(lines.mapped('principal'), [30000.0, 30000.0, 40000.0])
        self.assertEqual(lines.mapped('interest'), [500.0, 350.0, 200.0])
        self.assertEqual(lines.mapped('opening_balance'), [100000.0, 70000.0, 40000.0])
        self.assertEqual((loan.payment_count, loan.date_first_payment), (3, date(2025, 2, 1)))
        loan.action_confirm()
        self.assertEqual(self._lines(loan).mapped('principal'), [30000.0, 30000.0, 40000.0])
        self._draw(loan)
        self.assertEqual(self._lines(loan).mapped('interest'), [500.0, 350.0, 200.0])
        move = self._pay(self._lines(loan)[0])
        self.assertEqual(self._entry(move), {
            self.long_term_account.code: (30000.0, 0.0, 30000.0),
            self.interest_account.code: (500.0, 0.0, 500.0),
            self.outstanding_payments.code: (0.0, 30500.0, -30500.0),
        })

    def test_import_instalments_semicolon(self):
        """ Date, instalment, interest, with a semicolon, day-first dates and decimal commas. """
        loan = self._imported_loan()
        self._import(loan, "01/02/2025;30500,00;500,00\n01/03/2025;30350,00;350,00\n01/04/2025;40200,00;200,00\n",
                     columns='instalment')
        lines = self._lines(loan)
        self.assertEqual(lines.mapped('principal'), [30000.0, 30000.0, 40000.0])
        self.assertEqual(lines.mapped('amount'), [30500.0, 30350.0, 40200.0])

    def test_import_xlsx(self):
        import openpyxl  # the library of the import

        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(['Due date', 'Principal', 'Interest'])
        sheet.append([date(2025, 2, 1), 50000, 500.0])
        sheet.append([date(2025, 3, 1), 50000, 250.0])
        content = io.BytesIO()
        book.save(content)
        loan = self._imported_loan()
        self._import(loan, content.getvalue(), filename='lender.xlsx')
        self.assertEqual(self._lines(loan).mapped('principal'), [50000.0, 50000.0])
        self.assertEqual(self._lines(loan).mapped('interest'), [500.0, 250.0])

    def test_import_validation(self):
        loan = self._imported_loan()
        cases = {
            'sum': "2025-02-01,30000,500\n2025-03-01,30000,350\n",
            'dates': "2025-03-01,50000,500\n2025-02-01,50000,350\n",
            'before start': "2024-12-01,50000,500\n2025-02-01,50000,350\n",
            'not a date': "2025-02-01,50000,500\nnext month,50000,350\n",
            'not a number': "2025-02-01,50000,500\n2025-03-01,fifty,350\n",
            'negative interest': "2025-02-01,50000,-5\n2025-03-01,50000,350\n",
            'empty': "Date,Principal,Interest\n",
        }
        for case, content in cases.items():
            with self.subTest(case=case), self.assertRaises(UserError):
                self._import(loan, content)
        with self.assertRaises(UserError):
            # an instalment lower than its interest
            self._import(loan, "2025-02-01,400,500\n2025-03-01,100350,350\n", columns='instalment')
        self.assertFalse(loan.line_ids)
        # only for an imported schedule
        with self.assertRaises(UserError):
            self._import(self._create_loan(confirm=False), SCHEDULE)

    def test_edit_imported_line(self):
        """ An unpaid imported line is changed by hand, the last one takes the difference. """
        loan = self._imported_loan()
        self._import(loan, SCHEDULE)
        loan.action_confirm()
        self._draw(loan)
        lines = self._lines(loan)
        lines[0].write({'principal': 35000.0, 'interest': 510.0})
        self.assertEqual(self._lines(loan).mapped('principal'), [35000.0, 30000.0, 35000.0])
        loan.action_compute_schedule()
        self.assertEqual(self._lines(loan).mapped('principal'), [35000.0, 30000.0, 35000.0])
        self.assertEqual(self._lines(loan)[0].interest, 510.0)

    def test_reimport_after_payment(self):
        """ The paid lines stay; the new file schedules the principal left. """
        loan = self._imported_loan()
        self._import(loan, SCHEDULE)
        loan.action_confirm()
        self._draw(loan)
        self._pay(self._lines(loan)[0])
        with self.assertRaises(UserError):
            # dated before the paid line
            self._import(loan, "2025-01-15,70000,300\n")
        self._import(loan, "2025-03-01,20000,350\n2025-04-01,20000,200\n2025-05-01,30000,100\n")
        lines = self._lines(loan)
        self.assertEqual(lines.mapped('sequence'), [1, 2, 3, 4])
        self.assertEqual(lines.mapped('state'), ['posted', 'draft', 'draft', 'draft'])
        self.assertEqual(lines[1:].mapped('principal'), [20000.0, 20000.0, 30000.0])
        self.assertEqual(loan.payment_count, 4)

    def test_early_repayment_shortens(self):
        """ The principal repaid early comes off the last imported lines. """
        loan = self._imported_loan()
        self._import(loan, SCHEDULE)
        loan.action_confirm()
        self._draw(loan)
        self._pay(self._lines(loan)[0])
        self._repay(loan, date(2025, 2, 15), 50000.0, interest=100.0)
        lines = self._lines(loan)
        self.assertEqual(lines.mapped('principal'), [30000.0, 20000.0])
        self.assertEqual(loan.payment_count, 2)
        self.assertEqual(loan.outstanding_amount, 20000.0)

    def test_tranches_keep_imported_schedule(self):
        """ The imported schedule assumes the principal not drawn yet is drawn on the start date. """
        loan = self._imported_loan()
        self._import(loan, SCHEDULE)
        loan.action_confirm()
        self._draw(loan, date(2025, 1, 1), 60000.0)
        self.assertEqual(self._lines(loan).mapped('principal'), [30000.0, 30000.0, 40000.0])
        self._pay(self._lines(loan)[0])
        self._draw(loan, date(2025, 2, 10), 40000.0)
        self.assertEqual(self._lines(loan).mapped('principal'), [30000.0, 30000.0, 40000.0])
