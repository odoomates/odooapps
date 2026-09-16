""" The sources of the exchange rates. A source fetches the rates of the day against its base currency; the rates are
converted to the currency of each company afterwards, so any base works. Another module adds a source with a class
registered in `PROVIDERS` and in the selection of `res.company.rate_provider`. """
import logging
from datetime import datetime, timezone

import requests
from lxml import etree

from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 20


class RateProvider:
    """ A source of exchange rates. """
    code = None
    name = None
    needs_key = False
    key_field = None  # the field of the company holding the key

    def __init__(self, company):
        self.company = company

    def _get_key(self):
        return self.company.sudo()[self.key_field] if self.key_field else False

    def _hide_key(self, text):
        # the errors of requests show the URL, with the key
        key = self._get_key()
        return text.replace(key, '***') if key else text

    def _get_json(self, url, **params):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise UserError(self.company.env._('%(provider)s could not be reached: %(error)s',
                              provider=self.name, error=self._hide_key(str(error)))) from error
        try:
            return response.json()
        except ValueError as error:
            raise UserError(self.company.env._('%(provider)s answered with an unexpected response (HTTP %(status)s).',
                              provider=self.name, status=response.status_code)) from error

    def fetch(self):
        """ :return: (date of the rates, base currency code, {currency code: units per 1 base}) """
        raise NotImplementedError()


class EcbProvider(RateProvider):
    code = 'ecb'
    name = 'European Central Bank'
    url = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'

    def fetch(self):
        try:
            response = requests.get(self.url, timeout=TIMEOUT)
            response.raise_for_status()
            root = etree.fromstring(response.content)
        except (requests.RequestException, etree.XMLSyntaxError) as error:
            raise UserError(self.company.env._('%(provider)s could not be reached: %(error)s', provider=self.name, error=error)) from error
        namespace = {'ecb': 'http://www.ecb.int/vocabulary/2002-08-01/eurofxref'}
        day = root.find('.//ecb:Cube[@time]', namespace)
        if day is None:
            raise UserError(self.company.env._('%s answered without rates.', self.name))
        rates = {cube.get('currency'): float(cube.get('rate')) for cube in day.findall('ecb:Cube', namespace)}
        return datetime.strptime(day.get('time'), '%Y-%m-%d').date(), 'EUR', rates


class FrankfurterProvider(RateProvider):
    code = 'frankfurter'
    name = 'Frankfurter'
    url = 'https://api.frankfurter.dev/v1/latest'

    def fetch(self):
        data = self._get_json(self.url, base='EUR')
        if not isinstance(data.get('rates'), dict):
            raise UserError(self.company.env._('%(provider)s answered without rates: %(message)s', provider=self.name,
                              message=data.get('message') or data))
        return datetime.strptime(data['date'], '%Y-%m-%d').date(), data['base'], data['rates']


class OpenExchangeRatesProvider(RateProvider):
    code = 'openexchangerates'
    name = 'Open Exchange Rates'
    needs_key = True
    key_field = 'rate_openexchangerates_key'
    url = 'https://openexchangerates.org/api/latest.json'

    def fetch(self):
        key = self._get_key()
        if not key:
            raise UserError(self.company.env._('Enter the App ID of Open Exchange Rates in the settings.'))
        data = self._get_json(self.url, app_id=key)
        if data.get('error') or not isinstance(data.get('rates'), dict):
            raise UserError(self.company.env._('%(provider)s refused the request: %(message)s', provider=self.name,
                              message=data.get('description') or data.get('message') or data))
        day = datetime.fromtimestamp(data['timestamp'], tz=timezone.utc).date()
        return day, data['base'], data['rates']


class ExchangeRateApiProvider(RateProvider):
    code = 'exchangerate_api'
    name = 'ExchangeRate-API'
    key_field = 'rate_exchangerate_api_key'

    def fetch(self):
        key = self._get_key()
        if key:
            data = self._get_json('https://v6.exchangerate-api.com/v6/%s/latest/USD' % key)
        else:
            # the free feed without key, updated once a day
            data = self._get_json('https://open.er-api.com/v6/latest/USD')
        rates = data.get('conversion_rates') or data.get('rates')
        if data.get('result') != 'success' or not isinstance(rates, dict):
            raise UserError(self.company.env._('%(provider)s refused the request: %(message)s', provider=self.name,
                              message=data.get('error-type') or data))
        day = datetime.fromtimestamp(data['time_last_update_unix'], tz=timezone.utc).date()
        return day, data['base_code'], rates


PROVIDERS = {provider.code: provider for provider in (
    EcbProvider, FrankfurterProvider, OpenExchangeRatesProvider, ExchangeRateApiProvider,
)}
