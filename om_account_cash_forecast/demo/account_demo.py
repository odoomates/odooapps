from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.addons.account.models.chart_template import template


MODULE = 'om_account_cash_forecast'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_cash_forecast_xmlid(self, name):
        """ The xmlid of a demo record of the company, owned by the module: uninstalling it removes its demo """
        return f'{MODULE}.{self.env.company.id}_{name}'

    def _om_cash_forecast_demo_partner_id(self, xmlid):
        """ The id of a demo partner: given by its id, the field is not delayed by the loading of the demo
        partners of the other modules. """
        return (self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.partner']).id

    @template(model='account.cash.forecast.item', demo=True)
    def _get_om_cash_forecast_demo_item(self, template_code):
        company = self.env.company
        if company.parent_id:
            return {}
        today = fields.Date.context_today(self)
        loan_date = today + relativedelta(day=15)
        if loan_date < today:
            loan_date += relativedelta(months=1)
        items = {
            self._om_cash_forecast_xmlid('om_cash_forecast_salaries'): {
                'name': 'Salaries',
                'direction': 'out',
                'amount': 4200.0,
                'date': today + relativedelta(day=31),
                'recurrence': 'monthly',
                'note': 'Net salaries paid on the last day of the month.',
            },
            self._om_cash_forecast_xmlid('om_cash_forecast_social_charges'): {
                'name': 'Social charges and payroll taxes',
                'direction': 'out',
                'amount': 1350.0,
                'date': today + relativedelta(months=1, day=10),
                'recurrence': 'monthly',
            },
            self._om_cash_forecast_xmlid('om_cash_forecast_loan'): {
                'name': 'Bank loan instalment',
                'direction': 'out',
                'amount': 650.0,
                'date': loan_date,
                'recurrence': 'monthly',
                'date_end': loan_date + relativedelta(months=23),
                'note': 'Equipment loan, 24 instalments left.',
            },
            self._om_cash_forecast_xmlid('om_cash_forecast_vat'): {
                'name': 'VAT payment',
                'direction': 'out',
                'amount': 1800.0,
                'date': today + relativedelta(months=1, day=20),
                'recurrence': 'quarterly',
            },
            self._om_cash_forecast_xmlid('om_cash_forecast_customer_receipt'): {
                'name': 'Down payment of the new office project',
                'direction': 'in',
                'amount': 7500.0,
                'date': today + relativedelta(days=20),
                'recurrence': 'none',
                'partner_id': self._om_cash_forecast_demo_partner_id('base.res_partner_12'),
                'note': 'Agreed with the customer, invoiced when the order is signed.',
            },
        }
        for values in items.values():
            values.update({'company_id': company.id, 'currency_id': company.currency_id.id})
        return {xmlid: values for xmlid, values in items.items() if not self.ref(xmlid, raise_if_not_found=False)}
