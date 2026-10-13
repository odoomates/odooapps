import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.addons.account.models.chart_template import template

_logger = logging.getLogger(__name__)

MODULE = 'om_fiscal_year'
# manual tasks of the demo closing marked as done
DONE_TASKS = ('closing_task_customer_invoices', 'closing_task_vendor_bills', 'closing_task_bank')


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_fiscal_year_xmlid(self, name):
        """ The xmlid of a demo record of the company, owned by the module: uninstalling it removes its demo """
        return f'{MODULE}.{self.env.company.id}_{name}'

    def _om_fiscal_year_demo_years(self):
        """ :return: {xmlid: (date_from, date_to)} of the current and the previous fiscal years of the company """
        company = self.env.company
        current = company.compute_fiscalyear_dates(fields.Date.context_today(self))
        previous = company.compute_fiscalyear_dates(current['date_from'] - timedelta(days=1))
        return {
            self._om_fiscal_year_xmlid('om_fiscal_year_previous'): (previous['date_from'], previous['date_to']),
            self._om_fiscal_year_xmlid('om_fiscal_year_current'): (current['date_from'], current['date_to']),
        }

    def _om_fiscal_year_demo_retained_earnings(self, company):
        Account = self.env['account.account'].with_company(company)
        return (
            company.retained_earnings_account_id
            or Account.search([*Account._check_company_domain(company), ('account_type', '=', 'equity'),
                               ('name', 'ilike', 'Retained')], limit=1)
            or self.ref(self._om_fiscal_year_xmlid('om_fiscal_year_demo_retained_earnings'),
                        raise_if_not_found=False)
        )

    @template(model='account.account', demo=True)
    def _get_om_fiscal_year_demo_1_account(self, template_code):
        """ A retained earnings account to close the previous fiscal year, when the chart has none. """
        company = self.env.company
        if company.parent_id or self._om_fiscal_year_demo_retained_earnings(company):
            return {}
        Account = self.env['account.account'].with_company(company)
        domain = Account._check_company_domain(company)
        equity = Account.search([*domain, ('account_type', '=', 'equity')], limit=1, order='code')
        values = {'name': 'Retained Earnings', 'account_type': 'equity'}
        code = equity.code
        if code:
            # e.g. 301000 -> 301100
            step_size = 10 ** max(len(code) - 4, 0) if code.isdigit() else 0
            for step in range(1, 100):
                candidate = str(int(code) + step * step_size).zfill(len(code)) if step_size else f'{code}.{step}'
                if not Account.search_count([*domain, ('code', '=', candidate)], limit=1):
                    values['code'] = candidate
                    break
            else:
                return {}
        # a chart without codes gets an account without code
        return {self._om_fiscal_year_xmlid('om_fiscal_year_demo_retained_earnings'): values}

    @template(model='account.fiscal.year', demo=True)
    def _get_om_fiscal_year_demo_2_year(self, template_code):
        company = self.env.company
        if company.parent_id:
            return {}
        FiscalYear = self.env['account.fiscal.year']
        data = {}
        for xmlid, (date_from, date_to) in self._om_fiscal_year_demo_years().items():
            if self.ref(xmlid, raise_if_not_found=False) or FiscalYear.search_count([
                ('company_id', '=', company.id), ('date_from', '<=', date_to), ('date_to', '>=', date_from),
            ], limit=1):
                continue
            data[xmlid] = {
                'name': str(date_to.year) if date_from.year == date_to.year else f'{date_from.year}-{date_to.year}',
                'company_id': company.id,
                'date_from': date_from,
                'date_to': date_to,
            }
        return data

    @template(model='account.period.closing', demo=True)
    def _get_om_fiscal_year_demo_3_closing(self, template_code):
        company = self.env.company
        xmlid = self._om_fiscal_year_xmlid('om_period_closing_last_month')
        if company.parent_id or self.ref(xmlid, raise_if_not_found=False):
            return {}
        date_from = fields.Date.context_today(self) + relativedelta(months=-1, day=1)
        date_to = date_from + relativedelta(day=31)
        if self.env['account.period.closing'].search_count([
            ('company_id', '=', company.id), ('date_from', '<=', date_to), ('date_to', '>=', date_from),
        ], limit=1):
            return {}
        return {
            xmlid: {
                'company_id': company.id,
                'date_from': date_from,
                'date_to': date_to,
            },
        }

    def _om_fiscal_year_post_load_demo(self):
        """ Mark the first tasks of the demo month-end closing as done and close the previous fiscal year without
        locking it. Called again on the companies already done, it changes nothing. """
        company = self.env.company
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        closing = self.ref(self._om_fiscal_year_xmlid('om_period_closing_last_month'), raise_if_not_found=False)
        if closing and closing.state == 'open':
            task_names = set()
            for xmlid in DONE_TASKS:
                task = self.env.ref(f'{MODULE}.{xmlid}', raise_if_not_found=False)
                if task:
                    task_names.add(task.name)
            tasks = closing.check_ids.filtered(lambda check: check.is_manual and check.name in task_names)
            if tasks and not closing.check_ids.filtered('done'):
                tasks.write({'done': True, 'done_by_id': admin.id if admin else False,
                             'done_on': fields.Datetime.now()})
            closing.action_refresh()

        previous = self.ref(self._om_fiscal_year_xmlid('om_fiscal_year_previous'), raise_if_not_found=False)
        retained_earnings = self._om_fiscal_year_demo_retained_earnings(company)
        journal = self.ref('general', raise_if_not_found=False)
        if previous and previous.state == 'open' and retained_earnings and journal:
            try:
                with self.env.cr.savepoint():
                    previous._close(journal, retained_earnings, previous.date_to + timedelta(days=1), lock=False)
            except UserError as error:
                # e.g. draft entries in the previous year: it stays open
                _logger.info('Demo fiscal year %s of %s left open: %s', previous.name, company.name, error)
            except Exception:  # noqa: BLE001 the demo is not worth failing the installation
                _logger.exception('Error while closing the demo fiscal year of %s', company.name)

    def _post_load_demo_data(self, template_code):
        super()._post_load_demo_data(template_code)
        self._om_fiscal_year_post_load_demo()

    @api.model
    def _om_fiscal_year_post_load_demo_companies(self):
        for company in self.env['res.company'].search([('chart_template', '!=', False)], order='parent_path'):
            self.with_company(company).with_context(allowed_company_ids=company.ids)._om_fiscal_year_post_load_demo()


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def write(self, vals):
        # the demo data of the module is loaded on the companies with a chart when the module is set installed
        installing = len(self) == 1 and self.name == MODULE and self.state not in (
            'installed', 'to upgrade', 'to remove')
        res = super().write(vals)
        if installing and self.state == 'installed' and self.demo:
            self.env['account.chart.template'].sudo()._om_fiscal_year_post_load_demo_companies()
        return res
