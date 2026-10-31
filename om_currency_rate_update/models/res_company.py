import logging

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .rate_providers import CENTRAL_BANKS, PROVIDERS

_logger = logging.getLogger(__name__)

PROVIDER_SELECTION = [
    ('frankfurter', 'Frankfurter'),
    ('ecb', 'European Central Bank'),
    ('openexchangerates', 'Open Exchange Rates'),
    ('exchangerate_api', 'ExchangeRate-API'),
    ('central_bank', 'Central Bank (official rates)'),
]
# by country: "Kenya - Central Bank of Kenya"
CENTRAL_BANK_SELECTION = sorted(
    ((bank.code, '%s - %s' % (bank.country_name, bank.name)) for bank in CENTRAL_BANKS.values()),
    key=lambda item: item[1])
INTERVAL_STEPS = {
    'daily': relativedelta(days=1),
    'weekly': relativedelta(weeks=1),
    'monthly': relativedelta(months=1),
}
# consecutive failures after which the administrators are told
FAILURES_TO_NOTIFY = 3


class ResCompany(models.Model):
    _inherit = 'res.company'

    rate_interval = fields.Selection(
        [('manual', 'Manually'), ('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')],
        string='Update Currency Rates', default='manual', required=True)
    rate_provider = fields.Selection(PROVIDER_SELECTION, string='Rates Source', default='frankfurter', required=True)
    rate_fallback_provider = fields.Selection(
        PROVIDER_SELECTION, string='Backup Source',
        help="Gives the rates of the currencies the main source does not quote, or all of them when it fails.")
    rate_central_bank = fields.Selection(
        CENTRAL_BANK_SELECTION, string='Central Bank', compute='_compute_rate_central_bank', store=True, readonly=False,
        help="The bank whose official rates the Central Bank source reads; by default the bank of the country of the "
             "company.")
    rate_openexchangerates_key = fields.Char(string='Open Exchange Rates App ID', groups='base.group_system')
    rate_exchangerate_api_key = fields.Char(string='ExchangeRate-API Key', groups='base.group_system')
    rate_currency_ids = fields.Many2many(
        'res.currency', 'res_company_rate_currency_rel', 'company_id', 'currency_id', string='Currencies to Update',
        help="Leave empty to update every active currency.")
    rate_date_policy = fields.Selection(
        [('source', 'Date of the rates at the source'), ('today', 'Day of the update')],
        string='Date of the Rates', default='source', required=True)
    rate_max_change = fields.Float(
        string='Hold Back Changes Above (%)', default=20.0,
        help="A rate moving more than this percentage from the latest rate of the currency is not saved but reported "
             "in the result of the update, to be checked and entered by hand. 0 saves every rate.")
    rate_next_date = fields.Date(string='Next Update')
    rate_last_update = fields.Datetime(string='Last Update', readonly=True)
    rate_last_message = fields.Text(string='Last Update Result', readonly=True)
    rate_failure_count = fields.Integer(readonly=True)

    @api.depends('rate_provider', 'rate_fallback_provider', 'country_id')
    def _compute_rate_central_bank(self):
        for company in self:
            company.rate_central_bank = company.rate_central_bank or self._get_default_central_bank(
                (company.rate_provider, company.rate_fallback_provider), company.country_id)

    @api.model
    def _get_default_central_bank(self, providers, country):
        """ The bank of `country` when the Central Bank source is among `providers` """
        if 'central_bank' not in providers:
            return False
        return next((bank.code for bank in CENTRAL_BANKS.values() if bank.country == country.code), False)

    # -------------------------------------------------------------------------
    # Fetching
    # -------------------------------------------------------------------------

    def _get_rate_provider(self, code):
        self.ensure_one()
        provider_class = PROVIDERS.get(code)
        if not provider_class:
            raise UserError(_('The rates source %s is not available.', code))
        return provider_class(self)

    def _get_rate_currencies(self):
        """ The currencies whose rates are updated: the chosen ones, else the active ones """
        self.ensure_one()
        currencies = self.rate_currency_ids or self.env['res.currency'].search([('active', '=', True)])
        return currencies - self.currency_id

    def _compute_rates(self, base, source_rates, currencies):
        """ Convert the rates of a source, in units per 1 `base`, to units per 1 unit of the company currency.

        :return: {currency: rate} of the currencies the source quotes
        """
        self.ensure_one()
        source_rates = dict(source_rates, **{base: 1.0})
        company_rate = source_rates.get(self.currency_id.name)
        if not company_rate:
            return {}
        return {
            currency: source_rates[currency.name] / company_rate
            for currency in currencies
            if source_rates.get(currency.name)
        }

    def _fetch_currency_rates(self):
        """ The rates of the day from the source and, for what it misses, from the backup source.

        :return: (date, {currency: rate}, {currency: source name}, [messages])
        """
        self.ensure_one()
        currencies = self._get_rate_currencies()
        rates, sources, messages = {}, {}, []
        date = None
        codes = [self.rate_provider]
        if self.rate_fallback_provider and self.rate_fallback_provider != self.rate_provider:
            codes.append(self.rate_fallback_provider)
        for code in codes:
            missing = currencies.filtered(lambda currency: currency not in rates)
            if not missing:
                break
            provider = self._get_rate_provider(code)
            try:
                source_date, base, source_rates = provider.fetch()
            except UserError as error:
                messages.append(error.args[0])
                continue
            date = date or source_date
            for currency, rate in self._compute_rates(base, source_rates, missing).items():
                rates[currency] = rate
                sources[currency] = provider.name
        not_quoted = currencies.filtered(lambda currency: currency not in rates)
        if not_quoted and (rates or not messages):
            messages.append(_('Not quoted by the sources: %s', ', '.join(not_quoted.mapped('name'))))
        return date, rates, sources, messages

    def _update_currency_rates(self):
        """ Fetch and save the rates of the companies.

        :return: True when some rates are saved
        """
        saved_any = False
        for company in self:
            company = company.root_id
            date, rates, sources, messages = company._fetch_currency_rates()
            if company.rate_date_policy == 'today' or not date:
                date = fields.Date.context_today(company)
            saved, skipped = company._save_currency_rates(date, rates, sources)
            if skipped:
                held = [_('%(currency)s %(old)s → %(new)s from %(source)s', currency=name, old='%.6g' % old,
                          new='%.6g' % new, source=source) for name, old, new, source in skipped]
                messages.append(_('Held back, more than %(max)s%% away from the latest rate (check them and enter '
                                  'them by hand if they are right): %(currencies)s',
                                  max=company.rate_max_change, currencies='; '.join(held)))
            summary = (_('%(count)s rate(s) saved for %(date)s.', count=len(saved), date=date)
                       if saved else _('No rate saved.'))
            if saved:
                messages.insert(0, _('From %s', ', '.join(sorted({sources[currency] for currency in rates
                                                                    if currency.name in saved}))))
            company.sudo().write({
                'rate_last_update': fields.Datetime.now(),
                'rate_last_message': '\n'.join([summary] + messages),
                'rate_failure_count': 0 if saved else company.rate_failure_count + 1,
            })
            if not saved:
                _logger.warning('Currency rates of %s not updated: %s', company.name, '; '.join(messages))
                if company.rate_failure_count == FAILURES_TO_NOTIFY:
                    company._notify_rate_failure(messages)
            saved_any = saved_any or bool(saved)
        return saved_any

    def _save_currency_rates(self, date, rates, sources):
        """ :return: (names of the currencies saved,
                      [(name, latest rate, new rate, source)] of the currencies held back by the maximum change) """
        self.ensure_one()
        Rate = self.env['res.currency.rate'].sudo()
        # the technical rate is relative to the rate of the company currency, usually 1
        reference = Rate._get_last_rates_for_companies(self)[self]
        saved, skipped = [], []
        for currency, rate in rates.items():
            existing = Rate.search([('currency_id', '=', currency.id), ('company_id', '=', self.id),
                                    ('name', '=', date)], limit=1)
            # the latest rate of the currency, whatever its date; the first rate is always saved
            latest = Rate.search([('currency_id', '=', currency.id), ('company_id', 'in', (self.id, False))],
                                 order='name desc, company_id', limit=1).with_company(self)
            if self.rate_max_change and latest.company_rate and \
                    abs(rate / latest.company_rate - 1.0) * 100.0 > self.rate_max_change:
                skipped.append((currency.name, latest.company_rate, rate, sources[currency]))
                continue
            values = {'rate': rate * reference, 'rate_source': sources[currency]}
            if existing:
                existing.write(values)
            else:
                Rate.create(dict(values, currency_id=currency.id, company_id=self.id, name=date))
            saved.append(currency.name)
        return saved, skipped

    def _notify_rate_failure(self, messages):
        self.ensure_one()
        managers = self.env.ref('account.group_account_manager').sudo().user_ids.filtered(
            lambda user: self in user.company_ids and not user.share)
        if managers:
            self.env['mail.thread'].sudo().message_notify(
                partner_ids=managers.partner_id.ids,
                subject=_('Currency rates not updated'),
                body=Markup('<p>%s</p><p>%s</p>') % (
                    _('The currency rates of %(company)s could not be updated %(count)s times in a row.',
                      company=self.name, count=FAILURES_TO_NOTIFY),
                    '; '.join(messages)),
            )

    # -------------------------------------------------------------------------
    # Schedule and buttons
    # -------------------------------------------------------------------------

    @api.model
    def _cron_update_currency_rates(self):
        today = fields.Date.context_today(self)
        companies = self.search([
            ('parent_id', '=', False), ('rate_interval', '!=', 'manual'),
            '|', ('rate_next_date', '=', False), ('rate_next_date', '<=', today),
        ])
        for company in companies:
            try:
                with self.env.cr.savepoint():
                    company._update_currency_rates()
            except Exception:
                _logger.exception('Currency rates of %s not updated', company.name)
            company.rate_next_date = today + INTERVAL_STEPS[company.rate_interval]

    def _test_currency_rates(self):
        """ Fetch without saving. :return: text describing the result """
        self.ensure_one()
        date, rates, sources, messages = self.root_id._fetch_currency_rates()
        lines = []
        if rates:
            sample = sorted(rates.items(), key=lambda item: item[0].name)[:5]
            lines.append(_('%(count)s rate(s) available for %(date)s, e.g. %(sample)s',
                           count=len(rates), date=date,
                           sample=', '.join('1 %s = %.6f %s' % (self.currency_id.name, rate, currency.name)
                                            for currency, rate in sample)))
            lines.append(_('From %s', ', '.join(sorted(set(sources.values())))))
        return '\n'.join(lines + messages) or _('No rate available.')
