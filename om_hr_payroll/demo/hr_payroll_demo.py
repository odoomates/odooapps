import logging

import babel.dates
from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import get_lang

_logger = logging.getLogger(__name__)

# the salary components of the demo employees, by position among the employees paid: (code, amount)
DEMO_COMPONENTS = [
    [('HOUSING', 800.0), ('TRANSPORT', 150.0), ('MEAL', 120.0)],
    [('HOUSING', 600.0), ('TRANSPORT', 100.0)],
    [('TRANSPORT', 120.0), ('MEAL', 100.0)],
    [('HOUSING', 500.0)],
    [('HOUSING', 650.0), ('MEAL', 110.0)],
    [('TRANSPORT', 90.0)],
]
DEMO_COMPONENT_XMLIDS = {
    'HOUSING': 'om_hr_payroll.salary_component_housing',
    'TRANSPORT': 'om_hr_payroll.salary_component_transport',
    'MEAL': 'om_hr_payroll.salary_component_meal',
}


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    @api.model
    def _om_demo_periods(self):
        today = fields.Date.context_today(self)
        last_month = today + relativedelta(months=-1, day=1)
        this_month = today + relativedelta(day=1)
        return (last_month, last_month + relativedelta(day=31)), (this_month, this_month + relativedelta(day=31))

    @api.model
    def _om_demo_employees(self, company, date_from, date_to):
        """ :return: a few employees of the company in contract during the whole demo periods, with a wage. """
        employees = self.env['hr.employee'].search([('company_id', '=', company.id)], order='id')
        return employees.filtered(lambda employee: (
            employee.version_id.wage
            and employee.version_id.date_version <= date_from
            and employee.version_id.contract_date_start
            and employee.version_id.contract_date_start <= date_from
            and (not employee.version_id.contract_date_end or employee.version_id.contract_date_end >= date_to)
            and employee.resource_calendar_id
        ))[:len(DEMO_COMPONENTS)]

    @api.model
    def _om_demo_batch(self, company, employees, xmlid, date_from, date_to):
        """ :return: a batch of the company for the period, with the payslips of the employees computed. """
        month = babel.dates.format_date(date_from, format='MMMM y', locale=get_lang(self.env).code)
        run = self.with_company(company).create({
            'name': _('Salaries %s', month),
            'date_start': date_from,
            'date_end': date_to,
            'company_id': company.id,
        })
        self.env['ir.model.data'].create({
            'module': 'om_hr_payroll', 'name': xmlid, 'model': run._name, 'res_id': run.id, 'noupdate': True,
        })
        self.env['hr.payslip.employees'].with_company(company).with_context(active_id=run.id).create({
            'employee_ids': [Command.set(employees.ids)],
        }).compute_sheet()
        return run

    @api.model
    def _om_load_demo_payslips(self):
        """ Demo data: the monthly structure and some salary components on the running contracts of a few
        employees of each company, the batch of last month confirmed and the one of this month in draft.

        Done once per company: a company that already has its demo batches is left as it is. """
        structure = self.env.ref('om_hr_payroll.structure_monthly', raise_if_not_found=False)
        if not structure:
            return
        (last_from, last_to), (this_from, this_to) = self._om_demo_periods()
        for company in self.env['res.company'].search([]):
            last_xmlid = f'demo_payslip_run_last_month_{company.id}'
            this_xmlid = f'demo_payslip_run_this_month_{company.id}'
            if self.env.ref(f'om_hr_payroll.{last_xmlid}', raise_if_not_found=False):
                continue
            employees = self._om_demo_employees(company, last_from, this_to)
            if not employees:
                continue
            # the core demo keeps its wages: only the structure and the components are added
            for employee, components in zip(employees, DEMO_COMPONENTS):
                version = employee.version_id
                vals = {}
                if not version.struct_id:
                    vals['struct_id'] = structure.id
                existing = version.salary_component_ids.mapped('code')
                vals['salary_component_ids'] = [Command.create({
                    'component_id': self.env.ref(DEMO_COMPONENT_XMLIDS[code]).id,
                    'amount': amount,
                }) for code, amount in components if code not in existing]
                version.write(vals)

            last_run = self._om_demo_batch(company, employees, last_xmlid, last_from, last_to)
            # a bonus and union dues on one payslip of the month
            slip = last_run.slip_ids.sorted('id')[1 if len(last_run.slip_ids) > 1 else 0]
            for line in slip.input_line_ids:
                if line.code == 'BONUS':
                    line.amount = 500.0
                elif line.code == 'UNION':
                    line.amount = 25.0
            slip.compute_sheet()
            try:
                with self.env.cr.savepoint():
                    last_run.done_payslip_run()
            except UserError as error:
                # e.g. the salary rules have no accounts yet: the accounting demo confirms the batch then
                _logger.info('Demo payslip batch %s left in draft: %s', last_run.name, error)

            self._om_demo_batch(company, employees, this_xmlid, this_from, this_to)
