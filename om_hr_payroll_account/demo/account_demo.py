import logging

from odoo import api, models
from odoo.exceptions import UserError
from odoo.addons.account.models.chart_template import template

_logger = logging.getLogger(__name__)

# the accounts of the demo payroll: the account of the generic or of the US chart, else the first account of the type
# whose name contains one of the words, tried in turn, else any account of the type
DEMO_ACCOUNTS = {
    'expense': (['expense_salary', 'account_account_us_salaries'], 'expense', ['salar', 'remunerat', 'wage']),
    'withholding': (['employee_payroll_taxes', 'account_account_us_employee_payroll_taxes'],
                    'liability_current', ['payroll', 'withh']),
    'other': (['current_liabilities', 'account_account_us_current_liabilities'], 'liability_current',
              ['current liabilit', 'other social', 'other']),
    'payable': (['salary_payable', 'account_account_us_salary_payable'], 'liability_current',
                ['salar', 'remunerat', 'wage']),
}

# the demo salary rules and their accounts. The deductions are negative amounts: their liability is the debit
# account, so that they are credited on it.
DEMO_RULE_ACCOUNTS = [
    ('om_hr_payroll.hr_rule_basic', 'account_debit', 'expense'),
    ('om_hr_payroll.hr_rule_unpaid_leave', 'account_debit', 'expense'),
    ('om_hr_payroll.hr_rule_allowances', 'account_debit', 'expense'),
    ('om_hr_payroll.hr_rule_bonus', 'account_debit', 'expense'),
    ('om_hr_payroll.hr_rule_union_dues', 'account_debit', 'other'),
    ('om_hr_payroll.hr_rule_pension', 'account_debit', 'withholding'),
    ('om_hr_payroll.hr_rule_income_tax', 'account_debit', 'withholding'),
    ('om_hr_payroll.hr_rule_net', 'account_credit', 'payable'),
]


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @api.model
    def _om_payroll_demo_account(self, role, company):
        """ :return: the account of the company for this role of DEMO_ACCOUNTS """
        xml_ids, account_type, words = DEMO_ACCOUNTS[role]
        for xml_id in xml_ids:
            account = self.ref(xml_id, raise_if_not_found=False)
            if account:
                return account
        Account = self.env['account.account'].with_company(company)
        domain = [*Account._check_company_domain(company), ('account_type', '=', account_type)]
        # the net salary is matched with its payment
        order = 'reconcile desc, id' if role == 'payable' else 'id'
        for word in words:
            account = Account.search(domain + [('name', 'ilike', word)], order=order, limit=1)
            if account:
                return account
        return Account.search(domain, order=order, limit=1)

    @template(model='account.journal', demo=True)
    def _get_om_hr_payroll_demo_journal(self, template_code):
        # qualified by the module, so that uninstalling it removes its demo journal
        return {
            f'om_hr_payroll_account.{self.env.company.id}_salary_journal': {
                'name': 'Salaries',
                'code': 'SAL',
                'type': 'general',
                'show_on_dashboard': True,
                'sequence': 20,
            },
        }

    @template(model='hr.salary.rule', demo=True)
    def _get_om_hr_payroll_demo_rule_accounts(self, template_code):
        company = self.env.company
        data = {}
        for rule_xmlid, field, role in DEMO_RULE_ACCOUNTS:
            if not self.env.ref(rule_xmlid, raise_if_not_found=False):
                continue
            account = self._om_payroll_demo_account(role, company)
            if account:
                data.setdefault(rule_xmlid, {})[field] = account.id
        return data

    def _post_load_demo_data(self, template_code):
        super()._post_load_demo_data(template_code)
        self._om_hr_payroll_post_demo(self.env.company)

    @api.model
    def _om_hr_payroll_load_demo(self):
        """ Demo data installed with the module: the salary journal and the accounts of the rules, then the
        entries of the demo payslips. The template data of the module is loaded by the installation of the
        module only after its demo files, so it is loaded here first. """
        for company in self.env['res.company'].search([('chart_template', '!=', False)], order='parent_path'):
            ChartTemplate = self.with_company(company)
            data = ChartTemplate._get_chart_template_data(company.chart_template, True, 'om_hr_payroll_account')
            data.pop('template_data', None)
            if data:
                ChartTemplate._pre_reload_data(company, {}, data, force_update=True)
                ChartTemplate._pre_load_data(company.chart_template, company, {}, data)
                ChartTemplate._load_data(data)
            ChartTemplate._om_hr_payroll_post_demo(company)

    @api.model
    def _om_hr_payroll_post_demo(self, company):
        """ Put the demo payslips of the company in the salary journal and post the entries of the confirmed ones.
        The payslips may have been confirmed before the accounting was set up: they are confirmed again. """
        journal = self.env.ref(f'om_hr_payroll_account.{company.id}_salary_journal', raise_if_not_found=False)
        if not journal:
            return
        last_run = self.env.ref(f'om_hr_payroll.demo_payslip_run_last_month_{company.id}', raise_if_not_found=False)
        this_run = self.env.ref(f'om_hr_payroll.demo_payslip_run_this_month_{company.id}', raise_if_not_found=False)
        runs = (last_run or self.env['hr.payslip.run']) | (this_run or self.env['hr.payslip.run'])
        if not runs:
            return
        slips = runs.slip_ids
        for version in slips.version_id.filtered(lambda version: not version.journal_id):
            version.journal_id = journal
        runs.filtered(lambda run: run.journal_id != journal).journal_id = journal
        slips.filtered(lambda slip: not slip.move_id and slip.journal_id != journal).journal_id = journal

        # confirmed before the accounting was installed: confirmed again, which posts their entries
        to_post = slips.filtered(lambda slip: slip.state == 'done' and not slip.move_id).sorted('id')
        try:
            with self.env.cr.savepoint():
                if to_post:
                    to_post.write({'state': 'draft'})
                    to_post.action_payslip_done()
                if last_run and last_run.state == 'draft':
                    last_run.done_payslip_run()
        except UserError:
            _logger.exception('Error while posting the demo payslips of %s', company.name)
