from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestPayroll(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({'name': 'Payroll 40h'})
        rules = cls.env['hr.salary.rule'].create([{
            'name': 'Basic', 'code': 'BASIC', 'sequence': 1, 'category_id': cls.env.ref('om_hr_payroll.BASIC').id,
            'amount_select': 'code', 'amount_python_compute': 'result = contract.wage',
        }, {
            'name': 'House Rent', 'code': 'HRA', 'sequence': 3, 'category_id': cls.env.ref('om_hr_payroll.ALW').id,
            'amount_select': 'code', 'amount_python_compute': 'result = contract.hra',
        }, {
            'name': 'Bonus', 'code': 'BONUS', 'sequence': 4, 'category_id': cls.env.ref('om_hr_payroll.ALW').id,
            'amount_select': 'code', 'amount_python_compute': 'result = inputs.BONUS and inputs.BONUS.amount',
            'input_ids': [Command.create({'name': 'Bonus', 'code': 'BONUS'})],
        }, {
            'name': 'Tax', 'code': 'TAX', 'sequence': 150, 'category_id': cls.env.ref('om_hr_payroll.DED').id,
            'amount_select': 'percentage', 'amount_percentage': -10, 'amount_percentage_base': 'contract.wage',
        }])
        if 'account_debit' in rules._fields:
            # payroll accounting is installed: confirmed payslips are posted
            cls.env['account.journal'].create({'name': 'Payroll Test', 'code': 'PAYT', 'type': 'general'})
            rules.write({
                'account_debit': cls.env['account.account'].create({
                    'name': 'Payroll Expense Test', 'code': 'PAYEXPT', 'account_type': 'expense'}).id,
                'account_credit': cls.env['account.account'].create({
                    'name': 'Payroll Payable Test', 'code': 'PAYPAYT', 'account_type': 'liability_current'}).id,
            })
        rules |= cls.env.ref('om_hr_payroll.hr_rule_taxable') | cls.env.ref('om_hr_payroll.hr_rule_net')
        cls.structure = cls.env['hr.payroll.structure'].create({
            'name': 'Test Structure', 'code': 'TEST', 'parent_id': False, 'rule_ids': [Command.set(rules.ids)],
        })
        cls.employee = cls._create_employee('Payroll Employee')

    @classmethod
    def _create_employee(cls, name, wage=5000.0, **values):
        return cls.env['hr.employee'].create({
            'name': name, 'resource_calendar_id': cls.calendar.id, 'tz': 'UTC',
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1),
            'wage': wage, 'hra': 1000.0, 'struct_id': cls.structure.id, **values,
        })

    def _new_payslip(self, employee, date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)):
        with Form(self.env['hr.payslip']) as payslip_form:
            payslip_form.employee_id = employee
            payslip_form.date_from = date_from
            payslip_form.date_to = date_to
        return payslip_form.record

    @staticmethod
    def _totals(payslip):
        totals = {}
        for line in payslip.line_ids:
            totals[line.code] = totals.get(line.code, 0.0) + line.total
        return totals

    def test_employee_salary_structure(self):
        self.assertEqual(self.employee.current_version_id.struct_id, self.structure)
        self.assertEqual(self.employee.struct_id, self.structure)

    def test_employee_without_working_schedule(self):
        employee = self.env['hr.employee'].create({'name': 'Flexible Employee', 'resource_calendar_id': False})
        self.assertTrue(employee.current_version_id.is_fully_flexible)

    def test_payslip_computation(self):
        payslip = self._new_payslip(self.employee)
        self.assertEqual(payslip.version_id, self.employee.current_version_id)
        self.assertEqual(payslip.struct_id, self.structure)
        self.assertEqual(payslip.worked_days_line_ids.mapped(lambda line: (line.code, line.number_of_days)), [('WORK100', 21.0)])
        self.assertEqual(payslip.input_line_ids.mapped('code'), ['BONUS'])

        payslip.input_line_ids.amount = 250.0
        payslip.compute_sheet()
        self.assertTrue(payslip.number)
        self.assertEqual(self._totals(payslip), {
            'BASIC': 5000.0, 'HRA': 1000.0, 'BONUS': 250.0, 'GROSS': 6250.0, 'TAX': -500.0, 'NET': 5750.0,
        })

    def test_time_off_in_worked_days(self):
        work_entry_type = self.env['hr.work.entry.type'].create({
            'name': 'Unpaid Test', 'code': 'TESTUNPAID', 'count_as': 'absence',
            'requires_allocation': False, 'leave_validation_type': 'no_validation',
        })
        leave = self.env['hr.leave'].create({
            'employee_id': self.employee.id, 'work_entry_type_id': work_entry_type.id,
            'request_date_from': date(2026, 9, 7), 'request_date_to': date(2026, 9, 8),
        })
        if leave.state != 'validate':
            leave.action_approve()
        payslip = self._new_payslip(self.employee, date(2026, 9, 1), date(2026, 9, 30))
        leave_line = payslip.worked_days_line_ids.filtered(lambda line: line.code == 'TESTUNPAID')
        self.assertEqual((leave_line.number_of_days, leave_line.number_of_hours), (-2.0, -16.0))

    def test_amended_contract_is_paid_once(self):
        """ A contract amended during the period is paid with the amendment only, not with every version. """
        new_version = self.employee.create_version({'date_version': date(2026, 8, 16), 'wage': 6000.0})

        payslip = self._new_payslip(self.employee)
        self.assertEqual(payslip.version_id, new_version)
        self.assertEqual(sum(payslip.worked_days_line_ids.mapped('number_of_days')), 21.0)
        payslip.compute_sheet()
        self.assertEqual(self._totals(payslip)['BASIC'], 6000.0)

        run = self.env['hr.payslip.run'].create({'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31)})
        wizard = self.env['hr.payslip.employees'].create({'employee_ids': [Command.set(self.employee.ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        self.assertEqual(run.slip_ids.version_id, new_version)
        self.assertEqual(sum(run.slip_ids.worked_days_line_ids.mapped('number_of_days')), 21.0)
        self.assertEqual(self._totals(run.slip_ids)['BASIC'], 6000.0)

    def test_payslip_batch(self):
        other_employee = self._create_employee('Second Employee', wage=3000.0)
        run = self.env['hr.payslip.run'].create({'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31)})
        wizard = self.env['hr.payslip.employees'].create({'employee_ids': [Command.set((self.employee | other_employee).ids)]})
        with self.assertRaises(UserError):
            wizard.compute_sheet()
        wizard.with_context(active_id=run.id).compute_sheet()
        self.assertEqual(sorted(self._totals(slip)['NET'] for slip in run.slip_ids), [3700.0, 5500.0])
        run.done_payslip_run()
        self.assertEqual(set(run.slip_ids.mapped('state')), {'done'})
        with self.assertRaises(UserError):
            run.slip_ids.unlink()

    def test_refund(self):
        payslip = self._new_payslip(self.employee)
        payslip.action_payslip_done()
        action = payslip.refund_sheet()
        refund = self.env['hr.payslip'].search(action['domain'])
        self.assertTrue(refund.credit_note)
        self.assertEqual(refund.state, 'done')
        self.assertEqual(self._totals(refund)['NET'], self._totals(payslip)['NET'])

    def test_payroll_officer(self):
        officer = new_test_user(self.env, login='payroll_officer', groups='base.group_user,om_hr_payroll.group_hr_payroll_user')
        payslip = self._new_payslip(self.employee.with_user(officer)).with_user(officer)
        payslip.compute_sheet()
        self.assertEqual(self._totals(payslip)['NET'], 5500.0)

    def test_reports(self):
        payslip = self._new_payslip(self.employee)
        payslip.action_payslip_done()
        Report = self.env['ir.actions.report']
        for report in ('om_hr_payroll.report_payslip', 'om_hr_payroll.report_payslip_details'):
            html = Report._render_qweb_html(report, payslip.ids)[0].decode()
            self.assertIn('Payroll Employee', html)

        register = self.env.ref('om_hr_payroll.contrib_register_employees')
        wizard = self.env['payslip.lines.contribution.register'].create({'date_from': date(2026, 8, 1), 'date_to': date(2026, 8, 31)})
        action = wizard.with_context(active_ids=register.ids, discard_logo_check=True).print_report()
        values = self.env['report.om_hr_payroll.report_contribution_register'].with_context(active_ids=register.ids)\
            ._get_report_values([], data=action['data'])
        self.assertEqual(values['lines_total'][register.id], 5500.0)

    def test_send_by_email(self):
        self.employee.work_email = 'payroll.employee@example.com'
        payslip = self._new_payslip(self.employee)
        payslip.action_payslip_done()
        action = payslip.action_send_email()
        composer = Form(self.env['mail.compose.message'].with_context(action['context'])).save()
        self.assertEqual(composer.subject, f'Payslip: {payslip.number}')
        self.assertTrue(composer.attachment_ids)
