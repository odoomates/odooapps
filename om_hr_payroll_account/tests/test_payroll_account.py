from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPayrollAccount(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids = [Command.link(cls.env.ref('om_hr_payroll.group_hr_payroll_manager').id)]
        cls.expense_account = cls.company_data['default_account_expense']
        cls.payable_account = cls.env['account.account'].create({
            'name': 'Salaries Payable', 'code': 'SALPAY', 'account_type': 'liability_current',
        })
        cls.journal = cls.company_data['default_journal_misc']
        category = cls.env.ref('om_hr_payroll.BASIC')
        rules = cls.env['hr.salary.rule'].create([{
            'name': 'Basic', 'code': 'BASIC', 'sequence': 1, 'category_id': category.id,
            'amount_select': 'code', 'amount_python_compute': 'result = contract.wage',
            'account_debit': cls.expense_account.id, 'account_credit': cls.payable_account.id,
        }, {
            'name': 'Tax', 'code': 'TAX', 'sequence': 150, 'category_id': cls.env.ref('om_hr_payroll.DED').id,
            'amount_select': 'percentage', 'amount_percentage': -10, 'amount_percentage_base': 'contract.wage',
        }])
        rules |= cls.env.ref('om_hr_payroll.hr_rule_net')
        structure = cls.env['hr.payroll.structure'].create({
            'name': 'Accounting Structure', 'code': 'ACC', 'parent_id': False, 'rule_ids': [Command.set(rules.ids)],
            'company_id': cls.env.company.id,
        })
        calendar = cls.env['resource.calendar'].create({'name': 'Payroll 40h', 'company_id': cls.env.company.id})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Accounted Employee', 'resource_calendar_id': calendar.id, 'tz': 'UTC', 'company_id': cls.env.company.id,
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1), 'wage': 4000.0,
            'struct_id': structure.id,
        })

    def _new_payslip(self, env=None):
        with Form((env or self.env)['hr.payslip']) as payslip_form:
            payslip_form.employee_id = self.employee
            payslip_form.date_from = date(2026, 8, 1)
            payslip_form.date_to = date(2026, 8, 31)
            # the journal is not cleared by the contract of the employee
            self.assertTrue(payslip_form.journal_id)
            payslip_form.journal_id = self.journal
        return payslip_form.record

    def _expense_balance(self, move):
        return sum(move.line_ids.filtered(lambda line: line.account_id == self.expense_account).mapped('balance'))

    def test_payslip_entry(self):
        payslip = self._new_payslip()
        payslip.action_payslip_done()
        move = payslip.move_id
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.journal_id, self.journal)
        self.assertEqual(move.date, date(2026, 8, 31))
        self.assertEqual(self._expense_balance(move), 4000.0)
        self.assertEqual(sum(move.line_ids.mapped('balance')), 0.0)

        action = payslip.refund_sheet()
        refund = self.env['hr.payslip'].search(action['domain'])
        self.assertEqual(refund.move_id.state, 'posted')
        self.assertEqual(self._expense_balance(refund.move_id), -4000.0)

    def test_cancel_payslip_removes_entry(self):
        payslip = self._new_payslip()
        payslip.action_payslip_done()
        move = payslip.move_id
        payslip.action_payslip_cancel()
        self.assertEqual(payslip.state, 'cancel')
        self.assertFalse(move.exists())

    def test_batch_journal(self):
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31), 'journal_id': self.journal.id,
        })
        wizard = self.env['hr.payslip.employees'].create({'employee_ids': [Command.set(self.employee.ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        self.assertEqual(run.slip_ids.journal_id, self.journal)
        run.done_payslip_run()
        self.assertEqual(run.slip_ids.move_id.journal_id, self.journal)

    def test_payroll_user_without_accounting_rights(self):
        officer = new_test_user(self.env, login='payroll_only', groups='base.group_user,om_hr_payroll.group_hr_payroll_user',
                                company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        self.assertFalse(officer.has_group('account.group_account_invoice'))
        payslip = self._new_payslip(self.env(user=officer))
        self.assertEqual(payslip.journal_id.company_id, self.env.company)
        payslip.with_user(officer).action_payslip_done()
        self.assertEqual(payslip.move_id.state, 'posted')
        self.assertEqual(payslip.move_id.company_id, self.env.company)

    def test_journal_of_another_company(self):
        other_journal = self.company_data_2['default_journal_misc'] if hasattr(self, 'company_data_2') else \
            self.setup_other_company()['default_journal_misc']
        payslip = self._new_payslip()
        with self.assertRaises(ValidationError):
            payslip.journal_id = other_journal

    def test_cancel_refused_when_entry_is_locked(self):
        payslip = self._new_payslip()
        payslip.action_payslip_done()
        move = payslip.move_id
        self.env.company.fiscalyear_lock_date = date(2026, 8, 31)
        with self.assertRaises(UserError):
            payslip.action_payslip_cancel()
        self.assertEqual(payslip.state, 'done')
        self.assertEqual(move.state, 'posted')

        # once reversed in accounting, the payslip can be cancelled and the entry stays
        self.env.company.fiscalyear_lock_date = False
        move._reverse_moves(default_values_list=[{'date': date(2026, 9, 1)}], cancel=True)
        payslip.action_payslip_cancel()
        self.assertEqual(payslip.state, 'cancel')
        self.assertTrue(move.exists())
