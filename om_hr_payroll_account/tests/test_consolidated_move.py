from datetime import date

from odoo import Command
from odoo.tests import tagged

from odoo.addons.om_hr_payroll_account.tests.test_payroll_account import TestPayrollAccount


@tagged('post_install', '-at_install')
class TestConsolidatedMove(TestPayrollAccount):
    """ A batch may post one entry for all its payslips instead of one entry each. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # the chart of a real payroll: the rules book the expense against a clearing account,
        # and the net rule owes the employee on a payable account, which carries their partner
        cls.payable_account.account_type = 'liability_payable'
        cls.clearing_account = cls.env['account.account'].create({
            'name': 'Salaries Clearing', 'code': 'SALCLR', 'account_type': 'liability_current',
        })
        basic_rule = cls.employee.version_id.struct_id.rule_ids.filtered(lambda rule: rule.code == 'BASIC')
        basic_rule.write({'account_debit': cls.expense_account.id,
                          'account_credit': cls.clearing_account.id})
        cls.env.ref('om_hr_payroll.hr_rule_net').write({'account_debit': cls.clearing_account.id,
                                                        'account_credit': cls.payable_account.id})
        cls.employee.work_contact_id = cls.env['res.partner'].create({'name': 'Accounted Employee'})
        cls.second_employee = cls.env['hr.employee'].create({
            'name': 'Second Accounted Employee', 'tz': 'UTC',
            'resource_calendar_id': cls.employee.resource_calendar_id.id,
            'company_id': cls.env.company.id,
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1), 'wage': 3000.0,
            'struct_id': cls.employee.struct_id.id,
            'work_contact_id': cls.env['res.partner'].create({'name': 'Second Accounted Employee'}).id,
        })

    def _new_run(self, consolidated, employees):
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31),
            'journal_id': self.journal.id, 'consolidated_move': consolidated,
        })
        wizard = self.env['hr.payslip.employees'].create({'employee_ids': [Command.set(employees.ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        return run

    def _lines_of(self, move, account):
        return move.line_ids.filtered(lambda line: line.account_id == account)

    def test_a_batch_posts_one_entry_for_all_its_payslips(self):
        run = self._new_run(True, self.employee | self.second_employee)
        run.done_payslip_run()

        move = run.slip_ids.move_id
        self.assertEqual(len(move), 1, 'the two payslips share one entry')
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.journal_id, self.journal)
        self.assertEqual(move.ref, run.name)
        self.assertEqual(sum(move.line_ids.mapped('balance')), 0.0)
        self.assertEqual(set(run.slip_ids.mapped('state')), {'done'})

        # the expense of the two employees is added up on one line, 4000 + 3000
        expense_lines = self._lines_of(move, self.expense_account)
        self.assertEqual(len(expense_lines), 1)
        self.assertEqual(expense_lines.balance, 7000.0)
        self.assertFalse(expense_lines.partner_id, 'the expense is not owed to anyone in particular')

        # what is owed to each employee keeps its own line, so a payment can be matched with it
        payable_lines = self._lines_of(move, self.payable_account)
        self.assertEqual(len(payable_lines), 2)
        # the net salary is what is owed: 90% of the wages, the tax rule deducting 10%
        self.assertEqual(sum(payable_lines.mapped('balance')), -6300.0)
        self.assertEqual(payable_lines.mapped('partner_id'),
                         (self.employee | self.second_employee).work_contact_id)

    def test_a_batch_without_the_setting_posts_one_entry_per_payslip(self):
        run = self._new_run(False, self.employee | self.second_employee)
        run.done_payslip_run()

        self.assertEqual(len(run.slip_ids.move_id), 2)
        self.assertEqual(set(run.slip_ids.move_id.mapped('state')), {'posted'})
        for slip in run.slip_ids:
            self.assertEqual(sum(slip.move_id.line_ids.mapped('balance')), 0.0)

    def test_the_payslips_keep_their_own_dates(self):
        run = self._new_run(True, self.employee | self.second_employee)
        early = run.slip_ids.filtered(lambda slip: slip.employee_id == self.employee)
        early.date = date(2026, 8, 20)
        run.done_payslip_run()

        # the entry is dated after the payslips it posts, and no payslip took another one's date
        self.assertEqual(run.slip_ids.move_id.date, date(2026, 8, 31))
        self.assertEqual(early.date, date(2026, 8, 20))

    def test_a_payslip_of_the_batch_confirmed_alone_keeps_its_entry(self):
        run = self._new_run(True, self.employee | self.second_employee)
        first = run.slip_ids[0]
        first.action_payslip_done()
        self.assertTrue(first.move_id, 'a payslip confirmed on its own posts its own entry')

        run.done_payslip_run()
        others = run.slip_ids - first
        self.assertTrue(others.move_id)
        self.assertNotEqual(others.move_id, first.move_id)
        self.assertEqual(sum(others.move_id.line_ids.mapped('balance')), 0.0)
