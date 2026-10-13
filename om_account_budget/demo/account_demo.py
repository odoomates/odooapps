import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, fields, models

from odoo.addons.account.models.chart_template import template

_logger = logging.getLogger(__name__)

MODULE = 'om_account_budget'

# planned revenues of the analytic budgets of next year, per month
OPTIMISTIC_REVENUES = [10000, 10000, 12000, 15000, 15000, 15000, 13000, 9000, 8000, 15000, 15000, 18000]
PESSIMISTIC_REVENUES = [9000, 8000, 10000, 14000, 16000, 13000, 10000, 8000, 7000, 12000, 18000, 18000]


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_budget_demo_xmlid(self, name, company=None):
        return '%s.%s_%s' % (MODULE, (company or self.env.company).id, name)

    def _om_budget_demo_accounts(self, account_types):
        company = self.env.company
        return self.env['account.account'].with_company(company).search([
            *self.env['account.account']._check_company_domain(company),
            ('account_type', 'in', account_types),
        ])

    @template(model='account.budget.position', demo=True)
    def _get_demo_data_om_budget_position(self, template_code):
        company = self.env.company
        income_accounts = self._om_budget_demo_accounts(['income', 'income_other'])
        expense_accounts = self._om_budget_demo_accounts(['expense', 'expense_direct_cost'])
        if not income_accounts or not expense_accounts:
            return {}
        return {
            self._om_budget_demo_xmlid('demo_position_sales'): {
                'name': 'Sales',
                'budget_type': 'revenue',
                'account_ids': [Command.set(income_accounts.ids)],
                'company_id': company.id,
            },
            self._om_budget_demo_xmlid('demo_position_expenses'): {
                'name': 'Operating Expenses',
                'budget_type': 'expense',
                'account_ids': [Command.set(expense_accounts.ids)],
                'company_id': company.id,
            },
        }

    @template(model='account.budget', demo=True)
    def _get_demo_data_om_budget(self, template_code):
        """ The budget of this year on the accounts, confirmed in `_om_budget_demo_post_load`, and two
        analytic budgets of next year """
        company = self.env.company
        year = fields.Date.context_today(self).year
        data = {}

        if self._om_budget_demo_accounts(['income', 'income_other']) and \
                self._om_budget_demo_accounts(['expense', 'expense_direct_cost']):
            lines = []
            for quarter in range(4):
                date_from = date(year, 3 * quarter + 1, 1)
                date_to = date_from + relativedelta(months=3, days=-1)
                for position, amount in (('demo_position_sales', 75000), ('demo_position_expenses', 12000)):
                    lines.append(Command.create({
                        'position_id': self._om_budget_demo_xmlid(position),
                        'date_from': date_from.strftime('%Y-%m-%d'),
                        'date_to': date_to.strftime('%Y-%m-%d'),
                        'planned_amount': amount,
                    }))
            data[self._om_budget_demo_xmlid('demo_budget_current_year')] = {
                'name': 'Budget %s' % year,
                'date_from': date(year, 1, 1).strftime('%Y-%m-%d'),
                'date_to': date(year, 12, 31).strftime('%Y-%m-%d'),
                'user_id': 'base.user_admin',
                'company_id': company.id,
                'line_ids': lines,
            }

        administrative = self.env.ref('analytic.analytic_administratif', raise_if_not_found=False)
        customer = self.env.ref('analytic.analytic_agrolait', raise_if_not_found=False)
        if administrative and customer:
            for name, label, admin_amount, revenues in (
                ('demo_budget_optimistic', 'Optimistic', 35000, OPTIMISTIC_REVENUES),
                ('demo_budget_pessimistic', 'Pessimistic', 55000, PESSIMISTIC_REVENUES),
            ):
                lines = [Command.create({
                    'analytic_account_id': administrative.id,
                    'budget_type': 'expense',
                    'date_from': date(year + 1, 1, 1).strftime('%Y-%m-%d'),
                    'date_to': date(year + 1, 12, 31).strftime('%Y-%m-%d'),
                    'planned_amount': admin_amount,
                })]
                for month, amount in enumerate(revenues, start=1):
                    date_from = date(year + 1, month, 1)
                    lines.append(Command.create({
                        'analytic_account_id': customer.id,
                        'budget_type': 'revenue',
                        'date_from': date_from.strftime('%Y-%m-%d'),
                        'date_to': (date_from + relativedelta(months=1, days=-1)).strftime('%Y-%m-%d'),
                        'planned_amount': amount,
                    }))
                data[self._om_budget_demo_xmlid(name)] = {
                    'name': 'Budget %s: %s' % (year + 1, label),
                    'date_from': date(year + 1, 1, 1).strftime('%Y-%m-%d'),
                    'date_to': date(year + 1, 12, 31).strftime('%Y-%m-%d'),
                    'user_id': 'base.user_admin',
                    'company_id': company.id,
                    'line_ids': lines,
                }
        return data

    def _post_load_demo_data(self, template_code):
        super()._post_load_demo_data(template_code)
        self._om_budget_demo_post_load(self.env.company)

    def _om_budget_demo_post_load(self, company):
        """ Confirm the budget of this year. Idempotent. """
        budget = self.env.ref(self._om_budget_demo_xmlid('demo_budget_current_year', company), raise_if_not_found=False)
        if not budget or budget.state != 'draft':
            return
        try:
            with self.env.cr.savepoint():
                budget.action_budget_confirm()
        except Exception:  # noqa: BLE001 - the demo data of the other modules must still load
            _logger.exception('Error while confirming the demo budget of %s', company.name)


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def write(self, vals):
        """ When the module is installed with demo data on companies that already have a chart, the
        accounting module loads its demo templates once the module is installed: complete them then. """
        was_installed = len(self) == 1 and self.state in ('installed', 'to upgrade', 'to remove')
        res = super().write(vals)
        if len(self) == 1 and self.name == MODULE and not was_installed and self.state == 'installed' and self.demo:
            for company in self.env['res.company'].search([('chart_template', '!=', False)], order='parent_path'):
                self.env['account.chart.template'].with_company(company)._om_budget_demo_post_load(company)
        return res
