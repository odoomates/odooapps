from datetime import date

import importlib.util
from pathlib import Path

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSalaryComponent(TransactionCase):
    """ The salary components replace the allowance fields of the contract: any company describes what it pays
        and the salary rules read it with components.<CODE>. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({'name': 'Components 40h'})
        cls.allowance = cls.env.ref('om_hr_payroll.ALW')
        cls.deduction = cls.env.ref('om_hr_payroll.DED')
        cls.housing = cls.env['hr.salary.component'].create({
            'name': 'Housing', 'code': 'HOUSING', 'category_id': cls.allowance.id, 'default_amount': 800.0,
        })
        cls.transport = cls.env['hr.salary.component'].create({
            'name': 'Transport', 'code': 'TRANSPORT', 'category_id': cls.allowance.id,
        })
        cls.advance = cls.env['hr.salary.component'].create({
            'name': 'Advance Repayment', 'code': 'ADVANCE', 'category_id': cls.deduction.id,
        })
        cls.structure = cls.env['hr.payroll.structure'].create({
            'name': 'Components Structure', 'code': 'COMPTEST', 'parent_id': False,
            'rule_ids': [Command.set((
                cls.env.ref('om_hr_payroll.hr_rule_basic')
                | cls.env.ref('om_hr_payroll.hr_rule_allowances')
                | cls.env.ref('om_hr_payroll.hr_rule_deductions')
                | cls.env.ref('om_hr_payroll.hr_rule_taxable')
                | cls.env.ref('om_hr_payroll.hr_rule_net')
            ).ids)],
        })

    def _create_employee(self, name='Component Employee', wage=4000.0, components=()):
        return self.env['hr.employee'].create({
            'name': name, 'resource_calendar_id': self.calendar.id, 'tz': 'UTC',
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1),
            'wage': wage, 'struct_id': self.structure.id,
            'salary_component_ids': [
                Command.create({'component_id': component.id, 'amount': amount})
                for component, amount in components
            ],
        })

    def _payslip(self, employee):
        payslip = self.env['hr.payslip'].create({
            'employee_id': employee.id, 'date_from': date(2026, 8, 1), 'date_to': date(2026, 8, 31),
            'struct_id': self.structure.id,
        })
        payslip.compute_sheet()
        return {line.code: line.total for line in payslip.line_ids}

    def test_code_must_be_an_identifier(self):
        """ The code is read as components.<CODE>, so it has to be a name Python accepts. """
        for code in ('HOUSE RENT', '2ND_HOME', 'house-rent', ''):
            with self.assertRaises(ValidationError):
                self.env['hr.salary.component'].create({'name': 'Wrong', 'code': code})

    def test_code_is_unique_per_company(self):
        with self.assertRaises(Exception):
            self.env['hr.salary.component'].create({'name': 'Housing again', 'code': 'HOUSING'})

    def test_component_set_once_per_version(self):
        """ A component added twice sets the amount of the line the version already carries.

        The framework writes the values of a version a second time when the employee is created, so the
        model has to take a component it already holds as the same line.
        """
        employee = self._create_employee(components=[(self.housing, 500.0)])
        version = employee.current_version_id
        self.assertEqual(len(version.salary_component_ids), 1)
        version.write({
            'salary_component_ids': [Command.create({'component_id': self.housing.id, 'amount': 100.0})],
        })
        self.assertEqual(len(version.salary_component_ids), 1, 'still one line for the component')
        self.assertEqual(version.get_component('HOUSING'), 100.0, 'the amount given last is kept')

    def test_get_component(self):
        employee = self._create_employee(components=[(self.housing, 750.0)])
        version = employee.current_version_id
        self.assertEqual(version.get_component('HOUSING'), 750.0)
        self.assertEqual(version.get_component('TRANSPORT'), 0.0, 'a component the version has not is worth 0')

    def test_allowances_and_deductions_are_paid(self):
        """ The rules shipped with the module pay the allowance components and deduct the deduction ones. """
        employee = self._create_employee(components=[
            (self.housing, 800.0), (self.transport, 200.0), (self.advance, 300.0),
        ])
        totals = self._payslip(employee)
        self.assertEqual(totals['BASIC'], 4000.0)
        self.assertEqual(totals['ALW'], 1000.0, 'the housing and the transport components')
        self.assertEqual(totals['DED'], -300.0, 'the advance is entered positive and deducted')
        self.assertEqual(totals['GROSS'], 5000.0)
        self.assertEqual(totals['NET'], 4700.0)

    def test_rule_reads_one_component(self):
        """ A rule of its own for a component, so that it has its own line on the payslip. """
        rule = self.env['hr.salary.rule'].create({
            'name': 'Housing', 'code': 'HOUSING', 'sequence': 40, 'category_id': self.allowance.id,
            'amount_select': 'code', 'amount_python_compute': 'result = components.HOUSING',
        })
        self.structure.write({'rule_ids': [Command.link(rule.id)]})
        employee = self._create_employee(components=[(self.housing, 800.0)])
        totals = self._payslip(employee)
        self.assertEqual(totals['HOUSING'], 800.0)

    def test_unknown_component_is_zero(self):
        """ A rule reading a component the version has not is worth 0, it does not break the payslip. """
        rule = self.env['hr.salary.rule'].create({
            'name': 'Meal', 'code': 'MEAL', 'sequence': 45, 'category_id': self.allowance.id,
            'amount_select': 'code', 'amount_python_compute': 'result = components.MEAL',
        })
        self.structure.write({'rule_ids': [Command.link(rule.id)]})
        employee = self._create_employee(components=[(self.housing, 800.0)])
        totals = self._payslip(employee)
        self.assertEqual(totals['MEAL'], 0.0)

    def test_components_follow_the_new_version(self):
        """ A new version of the contract keeps what the employee is paid. """
        employee = self._create_employee(components=[(self.housing, 800.0)])
        # a version of an employee is unique by date
        copied = employee.current_version_id.copy({'date_version': date(2026, 7, 1)})
        self.assertEqual(copied.get_component('HOUSING'), 800.0)

    def test_default_amount_proposed(self):
        line = self.env['hr.version.salary.component'].new({'component_id': self.housing.id})
        line._onchange_component_id()
        self.assertEqual(line.amount, 800.0, 'the default amount of the component is proposed')


@tagged('post_install', '-at_install')
class TestComponentMigration(TransactionCase):
    """ The rewriting of the salary rules done by the upgrade to 2.0.0. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        path = Path(__file__).parent.parent / 'migrations' / '2.0.0' / 'post-migrate.py'
        spec = importlib.util.spec_from_file_location('om_hr_payroll_post_migrate', path)
        cls.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.script)

    def _migrated(self, code):
        return self.script.CODE_PATTERN.sub(
            lambda match: 'components.%s' % self.script.LEGACY_FIELDS[match.group(1)][0], code)

    def test_rule_code_rewritten(self):
        self.assertEqual(self._migrated('result = contract.hra'), 'result = components.HRA')
        self.assertEqual(self._migrated('result = contract.da + contract.meal_allowance'),
                         'result = components.DA + components.MEAL')
        self.assertEqual(self._migrated('result = employee.contract_id.travel_allowance'),
                         'result = components.TRAVEL',
                         'whatever leads to the contract is replaced with the components')
        self.assertEqual(self._migrated('result = contract.other_allowance * 2'),
                         'result = components.OTHER * 2')

    def test_other_code_left_alone(self):
        for code in ('result = contract.wage',
                     'result = categories.BASIC',
                     'result = contract.wage * 0.4  # was the hra base'):
            self.assertEqual(self._migrated(code), code)
