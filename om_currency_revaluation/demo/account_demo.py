import logging

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.addons.account.models.chart_template import template

_logger = logging.getLogger(__name__)

MODULE = 'om_currency_revaluation'

# approximate value in USD of one unit, to give the demo rates a realistic level
USD_VALUES = {
    'USD': 1.0, 'EUR': 1.09, 'GBP': 1.28, 'CHF': 1.13, 'CAD': 0.73, 'AUD': 0.66, 'NZD': 0.6, 'JPY': 0.0067,
    'CNY': 0.14, 'INR': 0.012, 'BRL': 0.18, 'MXN': 0.055, 'AED': 0.272, 'SAR': 0.267, 'ZAR': 0.055,
    'SEK': 0.095, 'NOK': 0.093, 'DKK': 0.146, 'PLN': 0.25, 'CZK': 0.043, 'HUF': 0.0027, 'TRY': 0.03,
}
# change of the rate from one month to the next, the oldest first
RATE_MOVES = (1.0, 1.012, 0.994, 1.018, 1.027, 1.035)


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _om_reval_xmlid(self, name):
        """ The xmlid of a demo record of the company, owned by the module: uninstalling it removes its demo """
        return f'{MODULE}.{self.env.company.id}_{name}'

    def _om_reval_demo_partner_id(self, xmlid):
        """ The id of a demo partner: given by its id, the field is not delayed by the loading of the demo
        partners of the other modules. """
        return (self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.partner']).id

    def _om_reval_demo_currency(self):
        """ The foreign currency of the demo: the euro, or the US dollar for the companies in euro """
        company = self.env.company
        return self.env.ref('base.USD' if company.currency_id.name == 'EUR' else 'base.EUR')

    def _om_reval_demo_rates(self):
        """ Monthly rates of the foreign currency for the last six months, in the format of the demo rates of the
        automatic currency rates module (same dates and values: the rates of the module installed first are kept). """
        company = self.env.company
        foreign = self._om_reval_demo_currency()
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
            xmlid = self._om_reval_xmlid(f'om_demo_rate_{foreign.name.lower()}_{months_ago}')
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
    def _get_om_reval_demo_1_currency(self, template_code):
        if self.env.company.parent_id:
            return {}
        foreign = self._om_reval_demo_currency()
        return {} if foreign.active else {foreign.id: {'active': True}}

    @template(model='res.currency.rate', demo=True)
    def _get_om_reval_demo_2_rate(self, template_code):
        # loaded together with the automatic currency rates module, the rates are its demo
        if self.env.company.parent_id or hasattr(self, '_om_rate_update_demo_rates'):
            return {}
        return self._om_reval_demo_rates()

    @template(model='res.company', demo=True)
    def _get_om_reval_demo_company(self, template_code):
        """ The journal and the accounts of the revaluation entries, when not set yet """
        company = self.env.company
        if company.parent_id:
            return {}
        values = {}
        if not company.currency_reval_journal_id:
            journal = company.currency_exchange_journal_id or self.ref('general', raise_if_not_found=False)
            if journal:
                values['currency_reval_journal_id'] = journal.id
        if not company.currency_reval_gain_account_id and company.income_currency_exchange_account_id:
            values['currency_reval_gain_account_id'] = company.income_currency_exchange_account_id.id
        if not company.currency_reval_loss_account_id and company.expense_currency_exchange_account_id:
            values['currency_reval_loss_account_id'] = company.expense_currency_exchange_account_id.id
        return {company.id: values} if values else {}

    @template(model='account.move', demo=True)
    def _get_om_reval_demo_move(self, template_code):
        """ An invoice and a bill in the foreign currency, still open, for the revaluation to show """
        company = self.env.company
        if company.parent_id:
            return {}
        foreign = self._om_reval_demo_currency()
        today = fields.Date.context_today(self)
        invoice_date = today + relativedelta(days=-75)
        bill_date = today + relativedelta(days=-50)
        moves = {
            self._om_reval_xmlid('om_reval_demo_invoice'): {
                'move_type': 'out_invoice',
                'partner_id': self._om_reval_demo_partner_id('base.res_partner_2'),
                'currency_id': foreign.id,
                'invoice_date': invoice_date,
                'delivery_date': invoice_date,
                'invoice_date_due': invoice_date + relativedelta(days=90),
                'invoice_line_ids': [
                    Command.create({'name': 'Office design study, export', 'quantity': 1, 'price_unit': 4800.0}),
                ],
            },
            self._om_reval_xmlid('om_reval_demo_bill'): {
                'move_type': 'in_invoice',
                'partner_id': self._om_reval_demo_partner_id('base.res_partner_4'),
                'ref': f'EXP/{bill_date.year}/0412',
                'currency_id': foreign.id,
                'invoice_date': bill_date,
                'delivery_date': bill_date,
                'invoice_date_due': bill_date + relativedelta(days=90),
                'invoice_line_ids': [
                    Command.create({'name': 'Imported office chairs', 'quantity': 10, 'price_unit': 165.0}),
                ],
            },
        }
        return {xmlid: values for xmlid, values in moves.items() if not self.ref(xmlid, raise_if_not_found=False)}

    def _om_reval_post_load_demo(self):
        """ Post the demo invoice and bill in the foreign currency. Called again, it changes nothing. """
        for xmlid in (self._om_reval_xmlid('om_reval_demo_invoice'), self._om_reval_xmlid('om_reval_demo_bill')):
            move = self.ref(xmlid, raise_if_not_found=False)
            if move and move.state == 'draft':
                try:
                    with self.env.cr.savepoint():
                        move.action_post()
                except Exception:  # noqa: BLE001 the demo is not worth failing the installation
                    _logger.exception('Error while posting the demo entry %s of %s', xmlid, self.env.company.name)

    def _post_load_demo_data(self, template_code):
        super()._post_load_demo_data(template_code)
        self._om_reval_post_load_demo()

    @api.model
    def _om_reval_post_load_demo_companies(self):
        for company in self.env['res.company'].search([('chart_template', '!=', False)], order='parent_path'):
            self.with_company(company).with_context(allowed_company_ids=company.ids)._om_reval_post_load_demo()


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def write(self, vals):
        # the demo data of the module is loaded on the companies with a chart when the module is set installed
        installing = len(self) == 1 and self.name == MODULE and self.state not in (
            'installed', 'to upgrade', 'to remove')
        res = super().write(vals)
        if installing and self.state == 'installed' and self.demo:
            self.env['account.chart.template'].sudo()._om_reval_post_load_demo_companies()
        return res
