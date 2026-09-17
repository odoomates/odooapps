from datetime import date

from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestYearToDate(TransactionCase):
    """ What the employee has already been paid in the year, which the cumulative rules are computed on. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({'name': 'YTD 40h'})
        cls.ytd_rule = cls.env['hr.salary.rule'].create({
            'name': 'Gross Year To Date', 'code': 'YTDGROSS', 'sequence': 190,
            'category_id': cls.env.ref('om_hr_payroll.NET').id,
            'amount_select': 'code',
            'amount_python_compute': 'result = ytd.GROSS',
        })
        rules = cls.ytd_rule | (cls.env.ref('om_hr_payroll.hr_rule_basic')
                                | cls.env.ref('om_hr_payroll.hr_rule_taxable')
                                | cls.env.ref('om_hr_payroll.hr_rule_net'))
        if 'account_debit' in rules._fields:
            # payroll accounting is installed: a confirmed payslip is posted, so the rules need accounts
            cls.env['account.journal'].create({'name': 'Payroll YTD', 'code': 'PAYYT', 'type': 'general'})
            rules.write({
                'account_debit': cls.env['account.account'].create({
                    'name': 'Payroll Expense YTD', 'code': 'PAYEXPYT', 'account_type': 'expense'}).id,
                'account_credit': cls.env['account.account'].create({
                    'name': 'Payroll Payable YTD', 'code': 'PAYPAYYT', 'account_type': 'liability_current'}).id,
            })
        cls.structure = cls.env['hr.payroll.structure'].create({
            'name': 'YTD Structure', 'code': 'YTDTEST', 'parent_id': False,
            'rule_ids': [Command.set(rules.ids)],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'YTD Employee', 'resource_calendar_id': cls.calendar.id, 'tz': 'UTC',
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1),
            'wage': 1000.0, 'struct_id': cls.structure.id,
        })

    def _payslip(self, month, confirm=False):
        with Form(self.env['hr.payslip']) as payslip_form:
            payslip_form.employee_id = self.employee
            payslip_form.date_from = date(2026, month, 1)
            payslip_form.date_to = date(2026, month, 28)
        payslip = payslip_form.record
        payslip.compute_sheet()
        if confirm:
            payslip.action_payslip_done()
        return payslip

    @staticmethod
    def _total(payslip, code):
        return round(sum(line.total for line in payslip.line_ids if line.code == code), 2)

    def test_nothing_paid_yet(self):
        payslip = self._payslip(2)
        self.assertEqual(self._total(payslip, 'YTDGROSS'), 0.0,
                         'the first payslip of the year has nothing behind it')

    def test_the_payslips_already_confirmed_count(self):
        self._payslip(2, confirm=True)
        self._payslip(3, confirm=True)
        payslip = self._payslip(4)
        self.assertEqual(self._total(payslip, 'YTDGROSS'), 2000.0, 'the gross of February and March')

    def test_the_payslip_being_computed_does_not_count(self):
        """ A rule needing the year with this period adds it itself, so the order of the rules is plain. """
        self._payslip(2, confirm=True)
        payslip = self._payslip(3)
        self.assertEqual(self._total(payslip, 'YTDGROSS'), 1000.0)
        self.assertEqual(self._total(payslip, 'GROSS'), 1000.0)

    def test_a_draft_payslip_does_not_count(self):
        self._payslip(2)  # left draft
        payslip = self._payslip(3)
        self.assertEqual(self._total(payslip, 'YTDGROSS'), 0.0,
                         'only what is confirmed has been paid')

    def test_a_refund_takes_back_what_it_refunds(self):
        confirmed = self._payslip(2, confirm=True)
        confirmed.refund_sheet()
        payslip = self._payslip(3)
        self.assertEqual(self._total(payslip, 'YTDGROSS'), 0.0,
                         'the refund of February cancels out its gross')

    def test_the_year_follows_the_fiscal_year_of_the_company(self):
        """ April to March, as India and the United Kingdom run it. """
        company = self.env.company
        if not hasattr(company, 'compute_fiscalyear_dates'):
            self.skipTest('accounting is not installed, there is no fiscal year to follow')
        company.write({'fiscalyear_last_day': 31, 'fiscalyear_last_month': '3'})
        self.assertEqual(
            self.env['hr.payslip']._get_year_start(date(2026, 6, 30), company), date(2026, 4, 1),
            'a payslip of June belongs to the year that started in April')
        self.assertEqual(
            self.env['hr.payslip']._get_year_start(date(2026, 2, 28), company), date(2025, 4, 1),
            'a payslip of February belongs to the year that started the April before')

    def test_the_year_before_does_not_count(self):
        company = self.env.company
        if hasattr(company, 'compute_fiscalyear_dates'):
            company.write({'fiscalyear_last_day': 31, 'fiscalyear_last_month': '12'})
        with Form(self.env['hr.payslip']) as payslip_form:
            payslip_form.employee_id = self.employee
            payslip_form.date_from = date(2025, 12, 1)
            payslip_form.date_to = date(2025, 12, 28)
        last_year = payslip_form.record
        last_year.compute_sheet()
        last_year.action_payslip_done()
        payslip = self._payslip(2)
        self.assertEqual(self._total(payslip, 'YTDGROSS'), 0.0,
                         'what was paid last year is not part of this year')
