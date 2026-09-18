from datetime import date

from odoo import Command
from odoo.exceptions import AccessError, UserError
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
            'name': 'Housing', 'code': 'HOUSING', 'sequence': 3,
            'category_id': cls.env.ref('om_hr_payroll.ALW').id,
            'amount_select': 'code', 'amount_python_compute': 'result = components.HOUSING',
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
        cls.housing = cls.env['hr.salary.component'].create({
            'name': 'Housing', 'code': 'HOUSING', 'category_id': cls.env.ref('om_hr_payroll.ALW').id,
            'default_amount': 1000.0,
        })
        cls.employee = cls._create_employee('Payroll Employee')

    @classmethod
    def _create_employee(cls, name, wage=5000.0, housing=1000.0, **values):
        return cls.env['hr.employee'].create({
            'name': name, 'resource_calendar_id': cls.calendar.id, 'tz': 'UTC',
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1),
            'wage': wage, 'struct_id': cls.structure.id,
            'salary_component_ids': [Command.create({
                'component_id': cls.housing.id, 'amount': housing,
            })],
            **values,
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
        self.assertEqual(payslip.worked_days_line_ids.mapped(lambda line: (line.code, line.number_of_days)),
                         [('WORK100', 21.0)])
        self.assertEqual(payslip.input_line_ids.mapped('code'), ['BONUS'])

        payslip.input_line_ids.amount = 250.0
        payslip.compute_sheet()
        self.assertTrue(payslip.number)
        self.assertEqual(self._totals(payslip), {
            'BASIC': 5000.0, 'HOUSING': 1000.0, 'BONUS': 250.0, 'GROSS': 6250.0, 'TAX': -500.0, 'NET': 5750.0,
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

        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31)})
        wizard = self.env['hr.payslip.employees'].create({'employee_ids': [Command.set(self.employee.ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        self.assertEqual(run.slip_ids.version_id, new_version)
        self.assertEqual(sum(run.slip_ids.worked_days_line_ids.mapped('number_of_days')), 21.0)
        self.assertEqual(self._totals(run.slip_ids)['BASIC'], 6000.0)

    def test_payslip_batch(self):
        other_employee = self._create_employee('Second Employee', wage=3000.0)
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31)})
        wizard = self.env['hr.payslip.employees'].create({
            'employee_ids': [Command.set((self.employee | other_employee).ids)]})
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

    def test_changes_are_tracked(self):
        rule = self.structure.rule_ids.filtered(lambda rule: rule.code == 'TAX')
        rule.amount_percentage = -12
        payslip = self._new_payslip(self.employee)
        payslip.compute_sheet()
        # the changes made in the transaction creating a record are not tracked
        self.env.flush_all()
        self.env.cr.precommit.run()
        payslip.action_payslip_done()
        self.env.flush_all()
        self.env.cr.precommit.run()
        self.env.invalidate_all()
        self.assertIn('-10.00 → <b>-12.00</b> <i>(Percentage (%))</i>', ''.join(rule.message_ids.mapped('body')))
        self.assertIn('<b>Done</b>', ''.join(payslip.message_ids.mapped('body')))

        # the payslip lines copy the rules, not their chatter
        lines = payslip.line_ids
        self.assertFalse(lines.message_follower_ids)
        self.assertFalse(self.env['mail.message'].search_count([('model', '=', 'hr.payslip.line')]))

    def test_payroll_analysis(self):
        department = self.env['hr.department'].create({'name': 'Payroll Analysis Dept'})
        employee = self._create_employee('Analysed Employee', department_id=department.id)
        payslip = self._new_payslip(employee)
        payslip.action_payslip_done()
        self.env['hr.payslip'].search(payslip.refund_sheet()['domain'])

        officer = new_test_user(self.env, login='payroll_analyst',
                                groups='base.group_user,om_hr_payroll.group_hr_payroll_user')
        Analysis = self.env['hr.payslip.analysis'].with_user(officer)
        groups = Analysis._read_group(
            [('employee_id', '=', employee.id), ('code', '=', 'NET')], ['department_id', 'credit_note'], ['total:sum'])
        self.assertEqual({credit_note: total for _department, credit_note, total in groups},
                         {False: 5500.0, True: -5500.0})
        self.assertEqual({dep for dep, _credit_note, _total in groups}, {department})

    def test_payroll_officer(self):
        officer = new_test_user(self.env, login='payroll_officer',
                                groups='base.group_user,om_hr_payroll.group_hr_payroll_user')
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
        wizard = self.env['payslip.lines.contribution.register'].create({
            'date_from': date(2026, 8, 1), 'date_to': date(2026, 8, 31)})
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

    def test_send_batch_payslips_by_email(self):
        self.employee.work_email = 'payroll.employee@example.com'
        without_email = self._create_employee('No Email Employee', wage=3000.0)
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31)})
        wizard = self.env['hr.payslip.employees'].create({
            'employee_ids': [Command.set((self.employee | without_email).ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        run.done_payslip_run()
        action = run.action_send_payslips()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('No Email Employee', action['params']['message'])
        sent = run.slip_ids.filtered(lambda slip: slip.employee_id == self.employee)
        message = sent.message_ids.filtered(lambda message: message.message_type == 'comment')
        self.assertEqual(len(message), 1)
        self.assertEqual(message.subject, f'Payslip: {sent.number}')
        self.assertTrue(message.attachment_ids)
        self.assertFalse((run.slip_ids - sent).message_ids.filtered(lambda message: message.message_type == 'comment'))

    def test_send_selected_payslips_by_email(self):
        self.employee.work_email = 'payroll.employee@example.com'
        done = self._new_payslip(self.employee)
        done.compute_sheet()
        done.action_payslip_done()
        draft = self._new_payslip(self.employee)
        action = self.env.ref('om_hr_payroll.action_send_selected_payslips').with_context(
            active_model='hr.payslip', active_ids=(done | draft).ids).run()
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('not confirmed', action['params']['message'])
        comments = (done | draft).message_ids.filtered(lambda message: message.message_type == 'comment')
        self.assertEqual(comments.model, 'hr.payslip')
        self.assertEqual(comments.res_id, done.id)
        self.assertEqual(len(comments), 1)

    def test_batch_payroll_analysis(self):
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31)})
        wizard = self.env['hr.payslip.employees'].create({'employee_ids': [Command.set(self.employee.ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        action = run.action_open_payroll_analysis()
        self.assertEqual(action['res_model'], 'hr.payslip.analysis')
        lines = self.env['hr.payslip.analysis'].search(action['domain'])
        # the batch is not confirmed yet: its draft payslips are analysed too
        self.assertEqual(lines.slip_id, run.slip_ids)
        self.assertEqual(
            sum(lines.filtered(lambda line: line.category_id.code == 'NET').mapped('total')),
            sum(run.slip_ids.line_ids.filtered(lambda line: line.category_id.code == 'NET').mapped('total')),
        )

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------

    def _officer(self, login='payroll_officer_sec', **values):  # noqa: D401
        return new_test_user(self.env, login=login,
                             groups='base.group_user,om_hr_payroll.group_hr_payroll_user', **values)

    def test_officer_cannot_change_salary_rules(self):
        officer = self._officer()
        rule = self.env.ref('om_hr_payroll.hr_rule_net').with_user(officer)
        self.assertTrue(rule.amount_python_compute or rule.amount_select)
        with self.assertRaises(AccessError):
            rule.write({'amount_select': 'code', 'amount_python_compute': 'result = 1'})
        with self.assertRaises(AccessError):
            self.structure.with_user(officer).write({'name': 'Changed'})
        manager = new_test_user(self.env, login='payroll_manager_sec',
                                groups='base.group_user,om_hr_payroll.group_hr_payroll_manager')
        self.structure.with_user(manager).write({'name': 'Changed'})
        self.assertEqual(self.structure.name, 'Changed')

    def test_officer_payslips(self):
        officer = self._officer()
        department = self.env['hr.department'].create({'name': 'Sales'})
        other = self._create_employee('Sales Employee', department_id=department.id)
        own_employee = self._create_employee('Officer Employee', user_id=officer.id)
        payslips = self._new_payslip(self.employee) | self._new_payslip(other) | self._new_payslip(own_employee)
        # officers see every payslip of their companies, with their lines
        self.assertEqual(self.env['hr.payslip'].with_user(officer).search([('id', 'in', payslips.ids)]), payslips)
        payslips.compute_sheet()
        self.assertEqual(len(self.env['hr.payslip.line'].with_user(officer).search([('slip_id', 'in', payslips.ids)])),
                         len(payslips.line_ids))
        # but do not confirm their own payslip
        own_payslip = payslips.filtered(lambda payslip: payslip.employee_id == own_employee).with_user(officer)
        for action in ('action_payslip_done', 'action_payslip_cancel', 'action_payslip_draft'):
            with self.assertRaises(UserError):
                getattr(own_payslip, action)()
        payslips.filtered(lambda payslip: payslip.employee_id == other).with_user(officer).action_payslip_done()
        own_payslip.with_user(self.env.user).action_payslip_done()
        self.assertEqual(own_payslip.state, 'done')

    def test_payslips_of_other_companies(self):
        company_2 = self.env['res.company'].create({'name': 'Payroll Company 2'})
        employee_2 = self._create_employee('Company 2 Employee', company_id=company_2.id)
        if 'journal_id' in self.env['hr.payslip']._fields:
            self.env['account.journal'].create({
                'name': 'Salaries', 'code': 'SAL2', 'type': 'general', 'company_id': company_2.id})
        payslip_2 = self.env['hr.payslip'].create({
            'employee_id': employee_2.id, 'company_id': company_2.id,
            'date_from': date(2026, 8, 1), 'date_to': date(2026, 8, 31),
        })
        officer = self._officer(company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        self.assertFalse(self.env['hr.payslip'].with_user(officer).search([('id', '=', payslip_2.id)]))
        # the payroll data is shared by the companies
        self.assertFalse(self.env.ref('om_hr_payroll.BASIC').company_id)
        self.assertFalse(self.env.ref('om_hr_payroll.structure_base').company_id)

    def test_batch_confirmation_keeps_processed_payslips(self):
        other_employee = self._create_employee('Rejected Employee', wage=3000.0)
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31)})
        wizard = self.env['hr.payslip.employees'].create({
            'employee_ids': [Command.set((self.employee | other_employee).ids)]})
        wizard.with_context(active_id=run.id).compute_sheet()
        done = run.slip_ids.filtered(lambda slip: slip.employee_id == self.employee)
        rejected = run.slip_ids - done
        done.action_payslip_done()
        rejected.action_payslip_cancel()
        done_lines = done.line_ids
        self.employee.current_version_id.wage = 9000.0
        run.done_payslip_run()
        self.assertEqual(rejected.state, 'cancel')
        self.assertEqual(done.line_ids, done_lines)
        self.assertEqual(self._totals(done)['BASIC'], 5000.0)

    def test_batch_of_another_company(self):
        company_2 = self.env['res.company'].create({'name': 'Batch Company 2'})
        run = self.env['hr.payslip.run'].create({
            'name': 'August', 'date_start': date(2026, 8, 1), 'date_end': date(2026, 8, 31), 'company_id': company_2.id,
        })
        wizard = self.env['hr.payslip.employees'].create({'employee_ids': [Command.set(self.employee.ids)]})
        with self.assertRaises(UserError):
            wizard.with_context(
                active_id=run.id, allowed_company_ids=[self.env.company.id, company_2.id]).compute_sheet()

    def test_a_confirmed_payslip_is_locked_for_officers(self):
        officer = self._officer(login='payroll_officer_lock')
        payslip = self._new_payslip(self.employee)
        payslip.action_payslip_done()
        as_officer = payslip.with_user(officer)
        with self.assertRaises(UserError):
            as_officer.compute_sheet()
        with self.assertRaises(UserError):
            as_officer.write({'date_from': date(2026, 7, 1)})
        with self.assertRaises(UserError):
            as_officer.line_ids[0].with_user(officer).write({'amount': 1.0})
        with self.assertRaises(UserError):
            as_officer.action_payslip_draft()
        # the trail of what happens to it stays writable
        as_officer.write({'paid': True})
        self.assertTrue(payslip.paid)

        manager = new_test_user(self.env, login='payroll_manager_lock',
                                groups='base.group_user,om_hr_payroll.group_hr_payroll_manager')
        payslip.with_user(manager).action_payslip_draft()
        self.assertEqual(payslip.state, 'draft')
        payslip.with_user(manager).compute_sheet()

    def test_only_payroll_users_generate_payslips(self):
        hr_user = new_test_user(self.env, login='plain_hr_user', groups='base.group_user,hr.group_hr_user')
        with self.assertRaises(AccessError):
            self.env['hr.payslip.employees'].with_user(hr_user).create(
                {'employee_ids': [Command.set(self.employee.ids)]})
        officer = self._officer(login='payroll_officer_generate')
        self.env['hr.payslip.employees'].with_user(officer).create({'employee_ids': [Command.set(self.employee.ids)]})

    def test_contracts_menu_for_officers(self):
        officer = self._officer()
        visible = self.env['ir.ui.menu'].with_user(officer)._visible_menu_ids()
        self.assertIn(self.env.ref('om_hr_payroll.hr_menu_contract').id, visible)
