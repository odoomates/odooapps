from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPayslipPayment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids = [Command.link(cls.env.ref('om_hr_payroll.group_hr_payroll_manager').id)]
        cls.expense_account = cls.company_data['default_account_expense']
        cls.salary_payable = cls.env['account.account'].create({
            'name': 'Salaries to Pay', 'code': 'SALTOPAY', 'account_type': 'liability_payable', 'reconcile': True,
        })
        cls.tax_payable = cls.env['account.account'].create({
            'name': 'Payroll Tax to Pay', 'code': 'PAYTAX', 'account_type': 'liability_current',
        })
        # the gross salary is credited on a clearing account, split between the net salary and the tax
        clearing = cls.env['account.account'].create({
            'name': 'Gross Salaries', 'code': 'SALGROSS', 'account_type': 'liability_current',
        })
        cls.journal = cls.company_data['default_journal_misc']
        cls.bank_journal = cls.company_data['default_journal_bank']
        rules = cls.env['hr.salary.rule'].create([{
            'name': 'Basic', 'code': 'BASIC', 'sequence': 1, 'category_id': cls.env.ref('om_hr_payroll.BASIC').id,
            'amount_select': 'code', 'amount_python_compute': 'result = contract.wage',
            'account_debit': cls.expense_account.id, 'account_credit': clearing.id,
        }, {
            'name': 'Tax', 'code': 'TAX', 'sequence': 150, 'category_id': cls.env.ref('om_hr_payroll.DED').id,
            'amount_select': 'percentage', 'amount_percentage': -10, 'amount_percentage_base': 'contract.wage',
            'account_debit': cls.tax_payable.id, 'account_credit': clearing.id,
        }])
        net_rule = cls.env.ref('om_hr_payroll.hr_rule_net')
        net_rule.write({'account_debit': clearing.id, 'account_credit': cls.salary_payable.id})
        structure = cls.env['hr.payroll.structure'].create({
            'name': 'Paid Structure', 'code': 'PAID', 'parent_id': False,
            'rule_ids': [Command.set((rules | net_rule).ids)], 'company_id': cls.env.company.id,
        })
        cls.calendar = cls.env['resource.calendar'].create({'name': 'Payroll 40h', 'company_id': cls.env.company.id})
        cls.structure = structure
        cls.employee = cls._create_employee('Paid Employee', 4000.0)
        cls.other_employee = cls._create_employee('Other Paid Employee', 3000.0)

    @classmethod
    def _create_employee(cls, name, wage):
        return cls.env['hr.employee'].create({
            'name': name, 'resource_calendar_id': cls.calendar.id, 'tz': 'UTC', 'company_id': cls.env.company.id,
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1), 'wage': wage,
            'struct_id': cls.structure.id,
        })

    def _confirmed_payslip(self, employee=None):
        with Form(self.env['hr.payslip']) as payslip_form:
            payslip_form.employee_id = employee or self.employee
            payslip_form.date_from = date(2026, 8, 1)
            payslip_form.date_to = date(2026, 8, 31)
            payslip_form.journal_id = self.journal
        payslip = payslip_form.record
        payslip.action_payslip_done()
        return payslip

    def _pay(self, payslips, amount=None, user=None):
        action = payslips.with_user(user or self.env.user).action_register_payment()
        with Form(self.env[action['res_model']].with_user(user or self.env.user)
                  .with_context(action['context'])) as wizard_form:
            wizard_form.journal_id = self.bank_journal
            wizard_form.payment_date = date(2026, 9, 1)
            if amount is not None:
                wizard_form.amount = amount
        return wizard_form.record.action_create_payments()

    def test_pay_a_payslip(self):
        payslip = self._confirmed_payslip()
        self.assertEqual(payslip.payment_state, 'not_paid')
        payable = payslip._get_salary_payable_lines()
        self.assertEqual(payable.balance, -3600.0)
        self.assertEqual(payable.partner_id, self.employee.work_contact_id)

        self._pay(payslip)
        payment = payslip.payment_ids
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.amount, 3600.0)
        self.assertEqual(payment.partner_id, self.employee.work_contact_id)
        self.assertEqual(payment.memo, payslip.number or payslip.name)
        self.assertTrue(payable.reconciled)
        self.assertIn(payslip.payment_state, ('paid', 'in_payment'))
        self.assertTrue(payslip.paid)
        self.assertEqual(payment.payslip_ids, payslip)
        with self.assertRaises(UserError):
            payslip.action_register_payment()

    def test_partial_payment(self):
        payslip = self._confirmed_payslip()
        self._pay(payslip, amount=1000.0)
        self.assertEqual(payslip.payment_state, 'partial')
        self.assertFalse(payslip.paid)
        self.assertEqual(sum(payslip._get_salary_payable_lines().mapped('amount_residual')), -2600.0)

        with self.assertRaises(UserError):
            self._pay(payslip, amount=3000.0)
        self._pay(payslip)
        self.assertEqual(sorted(payslip.payment_ids.mapped('amount')), [1000.0, 2600.0])
        self.assertIn(payslip.payment_state, ('paid', 'in_payment'))

    def test_pay_a_batch(self):
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31),
            'journal_id': self.journal.id,
        })
        wizard = self.env['hr.payslip.employees'].create({
            'employee_ids': [Command.set((self.employee | self.other_employee).ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        run.done_payslip_run()
        self.assertTrue(run.has_payslips_to_pay)

        action = run.action_register_payment()
        register = self.env[action['res_model']].with_context(action['context']).create({
            'journal_id': self.bank_journal.id})
        self.assertFalse(register.can_edit_amount)
        self.assertEqual(register.total_amount, 3600.0 + 2700.0)
        register.action_create_payments()

        payments = run.slip_ids.payment_ids
        self.assertEqual(len(payments), 2)
        self.assertEqual(sorted(payments.mapped('amount')), [2700.0, 3600.0])
        self.assertEqual(payments.partner_id, (self.employee | self.other_employee).work_contact_id)
        for slip in run.slip_ids:
            self.assertEqual(slip.payment_ids.partner_id, slip.employee_id.work_contact_id)
            self.assertIn(slip.payment_state, ('paid', 'in_payment'))
        self.assertFalse(run.has_payslips_to_pay)
        self.assertEqual(run.payment_count, 2)

    def test_refund(self):
        # refunded before being paid: nothing is left to pay on either
        payslip = self._confirmed_payslip()
        refund = self.env['hr.payslip'].search(payslip.refund_sheet()['domain'])
        self.assertEqual(payslip.payment_state, 'reversed')
        self.assertFalse(payslip._can_register_payment())
        self.assertFalse(refund._can_register_payment())
        with self.assertRaises(UserError):
            (payslip | refund).action_register_payment()

        # refunded once paid: the payment stays, the refund is not paid
        paid_payslip = self._confirmed_payslip(self.other_employee)
        self._pay(paid_payslip)
        refund = self.env['hr.payslip'].search(paid_payslip.refund_sheet()['domain'])
        self.assertIn(paid_payslip.payment_state, ('paid', 'in_payment'))
        self.assertFalse(refund._get_salary_payable_lines().reconciled)
        with self.assertRaises(UserError):
            refund.action_register_payment()

    def test_payment_without_entry(self):
        # with the accounting app, a payment method without outstanding account makes a payment without entry:
        # the net salary is matched with the bank statement later
        self.bank_journal.outbound_payment_method_line_ids.payment_account_id = False
        payslip = self._confirmed_payslip()
        with patch.object(type(self.env['account.move']), '_get_invoice_in_payment_state',
                          lambda self: 'in_payment'):
            self._pay(payslip)
            payslip.invalidate_recordset(['payment_state'])
            self.assertFalse(payslip.payment_ids.move_id)
            self.assertEqual(payslip.payment_state, 'in_payment')
            self.assertTrue(payslip.paid)
            self.assertFalse(payslip._get_salary_payable_lines().reconciled)
            with self.assertRaises(UserError):
                payslip.action_register_payment()

    def test_account_must_be_reconcilable(self):
        self.salary_payable.write({'account_type': 'liability_current', 'reconcile': False})
        payslip = self._confirmed_payslip()
        with self.assertRaises(UserError):
            self._pay(payslip)

    def test_payroll_manager_without_accounting_rights(self):
        manager = new_test_user(self.env, login='payroll_manager_only',
                                groups='base.group_user,om_hr_payroll.group_hr_payroll_manager',
                                company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        payslip = self._confirmed_payslip()
        with self.assertRaises(AccessError):
            self._pay(payslip, user=manager)
        self.assertEqual(payslip.payment_state, 'not_paid')

        accountant = new_test_user(self.env, login='payroll_accountant',
                                   groups='base.group_user,om_hr_payroll.group_hr_payroll_user,'
                                          'account.group_account_invoice',
                                   company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        self._pay(payslip, user=accountant)
        self.assertIn(payslip.payment_state, ('paid', 'in_payment'))
