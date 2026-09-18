from datetime import date

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRuleParameter(TransactionCase):
    """ Rates and scales are data the salary rules read by name, kept by date. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parameter = cls.env['hr.rule.parameter'].create({
            'name': 'Social Security Rate',
            'code': 'SS_RATE',
            'value_ids': [
                Command.create({'date_from': date(2025, 1, 1), 'value_number': 9.0}),
                Command.create({'date_from': date(2026, 1, 1), 'value_number': 10.0}),
            ],
        })

    def test_value_of_the_period(self):
        Parameter = self.env['hr.rule.parameter']
        self.assertEqual(Parameter.get_value('SS_RATE', date(2025, 6, 30)), 9.0)
        self.assertEqual(Parameter.get_value('SS_RATE', date(2026, 6, 30)), 10.0,
                         'the value that applies is the last one before the date')
        self.assertEqual(Parameter.get_value('SS_RATE', date(2030, 1, 1)), 10.0,
                         'the last value goes on applying')

    def test_missing_parameter_says_so(self):
        with self.assertRaises(UserError):
            self.env['hr.rule.parameter'].get_value('NOT_THERE', date(2026, 6, 30))

    def test_value_before_the_first_one_says_so(self):
        """ Paying zero quietly because a rate is not configured yet would be a wrong payslip. """
        with self.assertRaises(UserError):
            self.env['hr.rule.parameter'].get_value('SS_RATE', date(2024, 6, 30))

    def test_code_must_be_an_identifier(self):
        for code in ('SS RATE', '2_RATE', 'ss-rate'):
            with self.assertRaises(ValidationError):
                self.env['hr.rule.parameter'].create({'name': 'Wrong', 'code': code})

    def test_text_parameter(self):
        parameter = self.env['hr.rule.parameter'].create({
            'name': 'Filing Default', 'code': 'FILING_DEFAULT', 'value_type': 'text',
            'value_ids': [Command.create({'date_from': date(2026, 1, 1), 'value_text': 'SINGLE'})],
        })
        self.assertEqual(parameter._value_at(date(2026, 6, 30)), 'SINGLE')

    def test_value_changes_are_logged(self):
        value = self.parameter.value_ids.filtered(lambda value: value.value_number == 10.0)
        value.value_number = 11.0
        self.parameter.value_ids = [Command.create({'date_from': date(2027, 1, 1), 'value_number': 12.0})]
        value.unlink()
        bodies = ' '.join(self.parameter.message_ids.mapped('body'))
        self.assertIn('Value changed', bodies)
        self.assertIn('Value added', bodies)
        self.assertIn('Value removed', bodies)

        self.parameter.code = 'SS_RATE_2'
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.invalidate_all()
        self.assertIn('SS_RATE → <b>SS_RATE_2</b>', ''.join(self.parameter.message_ids.mapped('body')))

    def test_company_value_wins(self):
        company = self.env['res.company'].create({'name': 'Payroll Params Co'})
        self.env['hr.rule.parameter'].create({
            'name': 'Social Security Rate', 'code': 'SS_RATE', 'company_id': company.id,
            'value_ids': [Command.create({'date_from': date(2026, 1, 1), 'value_number': 7.5})],
        })
        Parameter = self.env['hr.rule.parameter']
        self.assertEqual(Parameter.get_value('SS_RATE', date(2026, 6, 30), company), 7.5)
        self.assertEqual(Parameter.get_value('SS_RATE', date(2026, 6, 30), self.env.company), 10.0,
                         'the other companies keep the shared value')


@tagged('post_install', '-at_install')
class TestSalaryBracket(TransactionCase):
    """ The bands of a tax, computed the way the country asks for. """

    def _bracket(self, computation, bands, key=False, code='TAX_TEST'):
        return self.env['hr.salary.bracket'].create({
            'name': 'Test Tax', 'code': code, 'computation': computation,
            'version_ids': [Command.create({
                'date_from': date(2026, 1, 1),
                'key': key,
                'line_ids': [Command.create(band) for band in bands],
            })],
        })

    def test_marginal_bands(self):
        """ Each slice at the rate of its own band, as most income taxes work. """
        bracket = self._bracket('marginal', [
            {'lower': 0, 'upper': 10000, 'rate': 0},
            {'lower': 10000, 'upper': 30000, 'rate': 10},
            {'lower': 30000, 'upper': 0, 'rate': 20},
        ])
        compute = lambda base: bracket.compute(base, date(2026, 6, 30))
        self.assertEqual(compute(5000), 0.0, 'below the first band')
        self.assertEqual(compute(20000), 1000.0, '10% of the 10000 above the floor')
        self.assertEqual(compute(50000), 2000.0 + 4000.0, '10% of 20000, then 20% of 20000')

    def test_excess_bands(self):
        """ The fixed amount of the band, plus its rate on what exceeds its floor. """
        bracket = self._bracket('excess', [
            {'lower': 0, 'upper': 10000, 'rate': 0, 'fixed_amount': 0},
            {'lower': 10000, 'upper': 30000, 'rate': 10, 'fixed_amount': 0},
            {'lower': 30000, 'upper': 0, 'rate': 20, 'fixed_amount': 2000},
        ])
        compute = lambda base: bracket.compute(base, date(2026, 6, 30))
        self.assertEqual(compute(20000), 1000.0)
        self.assertEqual(compute(50000), 2000.0 + 4000.0)

    def test_flat_band(self):
        """ A fixed amount per band, as a professional tax does. """
        bracket = self._bracket('flat', [
            {'lower': 0, 'upper': 15000, 'rate': 0, 'fixed_amount': 0},
            {'lower': 15000, 'upper': 25000, 'rate': 0, 'fixed_amount': 150},
            {'lower': 25000, 'upper': 0, 'rate': 0, 'fixed_amount': 200},
        ])
        compute = lambda base: bracket.compute(base, date(2026, 6, 30))
        self.assertEqual(compute(10000), 0.0)
        self.assertEqual(compute(20000), 150.0)
        self.assertEqual(compute(40000), 200.0)

    def test_table_per_key(self):
        """ The same tax with a table per filing status, per state or per pay frequency. """
        bracket = self._bracket('marginal', [{'lower': 0, 'upper': 0, 'rate': 10}], key='SINGLE')
        bracket.write({'version_ids': [Command.create({
            'date_from': date(2026, 1, 1), 'key': 'MARRIED',
            'line_ids': [Command.create({'lower': 0, 'upper': 0, 'rate': 5})],
        })]})
        self.assertEqual(bracket.compute(10000, date(2026, 6, 30), key='SINGLE'), 1000.0)
        self.assertEqual(bracket.compute(10000, date(2026, 6, 30), key='MARRIED'), 500.0)

    def test_table_of_the_period(self):
        bracket = self._bracket('marginal', [{'lower': 0, 'upper': 0, 'rate': 10}])
        bracket.write({'version_ids': [Command.create({
            'date_from': date(2027, 1, 1),
            'line_ids': [Command.create({'lower': 0, 'upper': 0, 'rate': 12})],
        })]})
        self.assertEqual(bracket.compute(10000, date(2026, 6, 30)), 1000.0,
                         'a payslip of 2026 is computed with the table of 2026')
        self.assertEqual(bracket.compute(10000, date(2027, 6, 30)), 1200.0)

    def test_missing_table_says_so(self):
        bracket = self._bracket('marginal', [{'lower': 0, 'upper': 0, 'rate': 10}])
        with self.assertRaises(UserError):
            bracket.compute(10000, date(2025, 6, 30))
        with self.assertRaises(UserError):
            bracket.compute(10000, date(2026, 6, 30), key='NO_SUCH_KEY')

    def test_band_ending_before_it_starts(self):
        with self.assertRaises(ValidationError):
            self._bracket('marginal', [{'lower': 1000, 'upper': 500, 'rate': 10}])


@tagged('post_install', '-at_install')
class TestParametersOnPayslip(TransactionCase):
    """ What a rule looks like once the rates are data. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['hr.rule.parameter'].create({
            'name': 'Pension Rate', 'code': 'PENSION_RATE',
            'value_ids': [Command.create({'date_from': date(2026, 1, 1), 'value_number': 5.0})],
        })
        cls.env['hr.salary.bracket'].create({
            'name': 'Income Tax', 'code': 'INCOME_TAX', 'computation': 'marginal',
            'version_ids': [Command.create({
                'date_from': date(2026, 1, 1),
                'line_ids': [
                    Command.create({'lower': 0, 'upper': 2000, 'rate': 0}),
                    Command.create({'lower': 2000, 'upper': 0, 'rate': 20}),
                ],
            })],
        })
        rules = cls.env['hr.salary.rule'].create([{
            'name': 'Pension', 'code': 'PENSION', 'sequence': 120,
            'category_id': cls.env.ref('om_hr_payroll.DED').id,
            'amount_select': 'code',
            'amount_python_compute': 'result = -categories.GROSS * parameters.PENSION_RATE / 100',
        }, {
            'name': 'Income Tax', 'code': 'TAX', 'sequence': 130,
            'category_id': cls.env.ref('om_hr_payroll.DED').id,
            'amount_select': 'code',
            'amount_python_compute': 'result = -brackets.INCOME_TAX.compute(categories.GROSS)',
        }])
        rules |= (cls.env.ref('om_hr_payroll.hr_rule_basic')
                  | cls.env.ref('om_hr_payroll.hr_rule_taxable')
                  | cls.env.ref('om_hr_payroll.hr_rule_net'))
        cls.structure = cls.env['hr.payroll.structure'].create({
            'name': 'Parameter Structure', 'code': 'PARAMTEST', 'parent_id': False,
            'rule_ids': [Command.set(rules.ids)],
        })
        cls.calendar = cls.env['resource.calendar'].create({'name': 'Parameters 40h'})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Parameter Employee', 'resource_calendar_id': cls.calendar.id, 'tz': 'UTC',
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1),
            'wage': 3000.0, 'struct_id': cls.structure.id,
        })

    def _payslip(self):
        with Form(self.env['hr.payslip']) as payslip_form:
            payslip_form.employee_id = self.employee
            payslip_form.date_from = date(2026, 6, 1)
            payslip_form.date_to = date(2026, 6, 30)
        payslip = payslip_form.record
        payslip.compute_sheet()
        return {line.code: round(line.total, 2) for line in payslip.line_ids}

    def test_rules_read_the_parameters_and_the_brackets(self):
        totals = self._payslip()
        self.assertEqual(totals['GROSS'], 3000.0)
        self.assertEqual(totals['PENSION'], -150.0, '5% of the gross, from the parameter')
        self.assertEqual(totals['TAX'], -200.0, '20% of the 1000 above the first band')
        self.assertEqual(totals['NET'], 3000.0 - 150.0 - 200.0)

    def test_changing_a_rate_is_entering_a_value(self):
        parameter = self.env['hr.rule.parameter']._get_parameter('PENSION_RATE')
        parameter.write({'value_ids': [Command.create({
            'date_from': date(2026, 6, 1), 'value_number': 6.0,
        })]})
        self.assertEqual(self._payslip()['PENSION'], -180.0, 'the new rate applies to the period')
