from datetime import date, datetime

from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLeaveDeduction(TransactionCase):
    """ The wage of the days of time off that are not paid is taken off the payslip.

    How much of a time off is paid comes from the rate of its time type, so the same rule serves an unpaid
    time off, a time off paid at half and a time off paid in full.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar = cls.env['resource.calendar'].create({'name': 'Leave 40h'})
        cls.structure = cls.env['hr.payroll.structure'].create({
            'name': 'Leave Structure', 'code': 'LEAVETEST', 'parent_id': False,
            'rule_ids': [Command.set((
                cls.env.ref('om_hr_payroll.hr_rule_basic')
                | cls.env.ref('om_hr_payroll.hr_rule_unpaid_leave')
                | cls.env.ref('om_hr_payroll.hr_rule_taxable')
                | cls.env.ref('om_hr_payroll.hr_rule_net')
            ).ids)],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Leave Employee', 'resource_calendar_id': cls.calendar.id, 'tz': 'UTC',
            'date_version': date(2026, 1, 1), 'contract_date_start': date(2026, 1, 1),
            'wage': 4400.0, 'struct_id': cls.structure.id,
        })

    def _time_type(self, name, **values):
        """ In Odoo 20 the type of a time off is a time type of the work entries. """
        return self.env['hr.work.entry.type'].create({
            'name': name,
            'code': name.upper().replace(' ', '_'),
            'count_as': 'absence',
            'requires_allocation': False,
            'time_off_selectable': True,
            **values,
        })

    def _take_leave(self, time_type, date_from, date_to):
        leave = self.env['hr.leave'].create({
            'name': time_type.name,
            'employee_id': self.employee.id,
            'work_entry_type_id': time_type.id,
            'request_date_from': date_from,
            'request_date_to': date_to,
        })
        if leave.state != 'validate':
            leave.sudo().action_approve()
        return leave

    def _payslip(self):
        """ Through the form, as the user and the batch wizard do: that is what fills the worked days. """
        with Form(self.env['hr.payslip']) as payslip_form:
            payslip_form.employee_id = self.employee
            payslip_form.date_from = date(2026, 6, 1)
            payslip_form.date_to = date(2026, 6, 30)
        payslip = payslip_form.record
        payslip.compute_sheet()
        return payslip

    @staticmethod
    def _totals(payslip):
        return {line.code: round(line.total, 2) for line in payslip.line_ids}

    def test_no_leave_pays_the_whole_wage(self):
        totals = self._totals(self._payslip())
        self.assertEqual(totals['BASIC'], 4400.0)
        self.assertEqual(totals['UNPAID'], 0.0, 'nothing is taken off without time off')
        self.assertEqual(totals['NET'], 4400.0)

    def test_unpaid_leave_is_deducted(self):
        """ 2 days of unpaid time off out of the worked days of June 2026. """
        self._take_leave(self._time_type('Unpaid', amount_rate=0.0), date(2026, 6, 8), date(2026, 6, 9))
        payslip = self._payslip()
        worked = {line.code: line for line in payslip.worked_days_line_ids}
        self.assertEqual(worked['UNPAID'].number_of_days, -2.0, 'the days of a time off are held negative')
        self.assertEqual(worked['UNPAID'].paid_rate, 0.0)
        totals = self._totals(payslip)
        scheduled = worked['WORK100'].number_of_days
        self.assertEqual(totals['UNPAID'], round(4400.0 * -2.0 / scheduled, 2))
        self.assertEqual(totals['NET'], round(4400.0 + totals['UNPAID'], 2))
        self.assertLess(totals['GROSS'], 4400.0, 'the gross is the pay earned in the period')

    def test_paid_leave_is_not_deducted(self):
        self._take_leave(self._time_type('Paid Time Off', amount_rate=1.0), date(2026, 6, 8), date(2026, 6, 9))
        totals = self._totals(self._payslip())
        self.assertEqual(totals['UNPAID'], 0.0, 'a time off paid in full takes nothing off')
        self.assertEqual(totals['NET'], 4400.0)

    def test_half_paid_leave_is_half_deducted(self):
        self._take_leave(self._time_type('Half Pay', amount_rate=0.5), date(2026, 6, 8), date(2026, 6, 9))
        payslip = self._payslip()
        worked = {line.code: line for line in payslip.worked_days_line_ids}
        scheduled = worked['WORK100'].number_of_days
        totals = self._totals(payslip)
        self.assertEqual(totals['UNPAID'], round(4400.0 * -1.0 / scheduled, 2),
                         'half of the 2 days is taken off')

    def test_type_marked_unpaid_is_deducted_whatever_its_rate(self):
        """ The Is Unpaid box of the Time Off application wins over the rate, which is left at 100%. """
        self._take_leave(self._time_type('Leave Without Pay', unpaid=True),
                         date(2026, 6, 8), date(2026, 6, 9))
        payslip = self._payslip()
        worked = {line.code: line for line in payslip.worked_days_line_ids}
        self.assertEqual(worked['LEAVE_WITHOUT_PAY'].paid_rate, 0.0)
        self.assertLess(self._totals(payslip)['UNPAID'], 0.0)

    def test_company_closure_is_paid(self):
        """ A closing day of the company carries no time type: it is paid, nothing is deducted. """
        self.env['resource.calendar.leaves'].create({
            'name': 'Company Closure',
            'calendar_id': self.calendar.id,
            'date_from': datetime(2026, 6, 8, 0, 0),
            'date_to': datetime(2026, 6, 9, 23, 59),
        })
        payslip = self._payslip()
        worked = {line.code: line for line in payslip.worked_days_line_ids}
        self.assertEqual(worked['GLOBAL'].paid_rate, 1.0, 'a closure without a time type is paid')
        self.assertEqual(self._totals(payslip)['UNPAID'], 0.0)
