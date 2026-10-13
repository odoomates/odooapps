from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestHrPayrollAccount(AccountTestInvoicingCommon):
    """ A payslip confirmed posts its journal entry, from the accounts of its salary rules. """

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.journal = cls.company_data['default_journal_misc']
        cls.journal.default_account_id = cls.company_data['default_account_expense']
        cls.employee = cls.env['hr.employee'].create({'name': 'John', 'company_id': cls.env.company.id})
        rules = cls.env['hr.salary.rule'].search([('code', 'in', ('BASIC', 'HRA', 'CA', 'PT', 'PF'))])
        rules.write({
            'account_debit': cls.company_data['default_account_expense'].id,
            'account_credit': cls.company_data['default_account_payable'].id,
        })
        cls.structure = cls.env['hr.payroll.structure'].create({
            'name': 'Software Developer',
            'code': 'SD',
            'company_id': cls.env.company.id,
            'parent_id': cls.env.ref('om_hr_payroll.structure_base').id,
            'rule_ids': [(6, 0, rules.ids)],
        })
        cls.date_from = date.today().replace(day=1)
        cls.date_to = cls.date_from + relativedelta(months=1, days=-1)
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Contract for John',
            'employee_id': cls.employee.id,
            'wage': 5000.0,
            'date_start': cls.date_from,
            'state': 'open',
            'type_id': cls.env.ref('om_hr_payroll.hr_contract_type_emp').id,
            'struct_id': cls.structure.id,
            'journal_id': cls.journal.id,
            'company_id': cls.env.company.id,
        })

    def test_00_hr_payslip(self):
        payslip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'journal_id': self.journal.id,
        })
        values = payslip.onchange_employee_id(self.date_from, self.date_to, self.employee.id)['value']
        payslip.write({
            'contract_id': values['contract_id'],
            'struct_id': values['struct_id'],
            'worked_days_line_ids': [(0, 0, line) for line in values['worked_days_line_ids']],
            'input_line_ids': [(0, 0, line) for line in values['input_line_ids']],
        })
        self.assertEqual(payslip.contract_id, self.contract)
        self.assertEqual(payslip.state, 'draft')

        payslip.compute_sheet()
        self.assertTrue(payslip.line_ids)

        # cancelled, then back to draft
        payslip.action_payslip_cancel()
        self.assertEqual(payslip.state, 'cancel')
        payslip.action_payslip_draft()

        payslip.action_payslip_done()
        self.assertEqual(payslip.state, 'done')
        self.assertTrue(payslip.move_id, "The journal entry of the payslip is not created")
        self.assertEqual(payslip.move_id.journal_id, self.journal)
        self.assertAlmostEqual(sum(payslip.move_id.line_ids.mapped('debit')),
                               sum(payslip.move_id.line_ids.mapped('credit')))
