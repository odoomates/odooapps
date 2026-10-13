from dateutil.relativedelta import relativedelta

from odoo import Command, fields, models
from odoo.addons.account.models.chart_template import template

# approximate value in USD of one unit, to give the demo rates a realistic level
USD_VALUES = {
    'USD': 1.0, 'EUR': 1.09, 'GBP': 1.28, 'CHF': 1.13, 'CAD': 0.73, 'AUD': 0.66, 'NZD': 0.6, 'JPY': 0.0067,
    'CNY': 0.14, 'INR': 0.012, 'BRL': 0.18, 'MXN': 0.055, 'AED': 0.272, 'SAR': 0.267, 'ZAR': 0.055,
    'SEK': 0.095, 'NOK': 0.093, 'DKK': 0.146, 'PLN': 0.25, 'CZK': 0.043, 'HUF': 0.0027, 'TRY': 0.03,
}
# change of the rate from one month to the next, the oldest first
RATE_MOVES = (1.0, 1.012, 0.994, 1.018, 1.027, 1.035)


MODULE = 'om_currency_rate_update'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_rate_update_xmlid(self, name):
        """ The xmlid of a demo record of the company, owned by the module: uninstalling it removes its demo """
        return f'{MODULE}.{self.env.company.id}_{name}'

    def _om_rate_update_demo_currency(self):
        """ The foreign currency of the demo: the euro, or the US dollar for the companies in euro """
        company = self.env.company
        return self.env.ref('base.USD' if company.currency_id.name == 'EUR' else 'base.EUR')

    def _om_rate_update_demo_rates(self):
        """ Monthly rates of the foreign currency for the last six months, in the format of the demo rates of the
        currency revaluation module (same dates and values: the rates of the module installed first are kept). """
        company = self.env.company
        foreign = self._om_rate_update_demo_currency()
        today = fields.Date.context_today(self)
        if company.currency_id.name in USD_VALUES:
            level = USD_VALUES[company.currency_id.name] / USD_VALUES[foreign.name]
        else:
            level = self.env['res.currency']._get_conversion_rate(company.currency_id, foreign, company, today)
        Rate = self.env['res.currency.rate']
        data = {}
        for index, move in enumerate(RATE_MOVES):
            date = today + relativedelta(months=index - len(RATE_MOVES) + 1, day=1)
            months_ago = len(RATE_MOVES) - 1 - index
            xmlid = self._om_rate_update_xmlid(f'om_demo_rate_{foreign.name.lower()}_{months_ago}')
            if self.ref(xmlid, raise_if_not_found=False) or Rate.search_count([
                ('currency_id', '=', foreign.id), ('company_id', '=', company.id), ('name', '=', date),
            ], limit=1):
                continue
            data[xmlid] = {
                'currency_id': foreign.id,
                'company_id': company.id,
                'name': date,
                'company_rate': round(level * move, 6),
            }
        return data

    @template(model='res.currency', demo=True)
    def _get_om_rate_update_demo_1_currency(self, template_code):
        if self.env.company.parent_id:
            return {}
        foreign = self._om_rate_update_demo_currency()
        return {} if foreign.active else {foreign.id: {'active': True}}

    @template(model='res.currency.rate', demo=True)
    def _get_om_rate_update_demo_2_rate(self, template_code):
        if self.env.company.parent_id:
            return {}
        return self._om_rate_update_demo_rates()

    @template(model='res.company', demo=True)
    def _get_om_rate_update_demo_company(self, template_code):
        """ The rates come from the European Central Bank, Frankfurter as backup, updated by hand: the demo does
        not call the sources on its own. """
        company = self.env.company
        if company.parent_id or company.rate_currency_ids:
            return {}
        return {
            company.id: {
                'rate_provider': 'ecb',
                'rate_fallback_provider': 'frankfurter',
                'rate_interval': 'manual',
                'rate_currency_ids': [Command.set(self._om_rate_update_demo_currency().ids)],
            },
        }
