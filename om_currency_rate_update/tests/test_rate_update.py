from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

import requests

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

GET = 'odoo.addons.om_currency_rate_update.models.rate_providers.requests.get'

FRANKFURTER = {'amount': 1.0, 'base': 'EUR', 'date': '2026-09-15',
               'rates': {'USD': 1.1539, 'GBP': 0.8558, 'INR': 110.7285}}
OPEN_EXCHANGE_RATES = {'timestamp': 1789430551, 'base': 'USD',
                       'rates': {'USD': 1.0, 'EUR': 0.8666, 'GBP': 0.7416, 'INR': 95.96, 'AED': 3.6725}}
ECB = (b"""<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" """
       b"""xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube><Cube time='2026-09-14'><Cube currency='USD' rate='1.1500'/><Cube currency='GBP' rate='0.8500'/></Cube></Cube>
</gesmes:Envelope>""")


class FakeResponse:
    def __init__(self, data=None, content=b'', status_code=200):
        self.data = data
        self.content = content
        self.status_code = status_code

    def json(self):
        if self.data is None:
            raise ValueError('not json')
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError('HTTP %s' % self.status_code)


def fake_get(responses):
    """ requests.get answering by the host of the URL, an exception for the hosts given one """
    def get(url, params=None, timeout=None):
        for host, response in responses.items():
            if host in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError('unexpected request to %s' % url)
    return get


@tagged('post_install', '-at_install')
class TestRateUpdate(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Currency = cls.env['res.currency'].with_context(active_test=False)
        cls.eur, cls.gbp, cls.inr, cls.aed = (Currency.search([('name', '=', code)])
                                              for code in ('EUR', 'GBP', 'INR', 'AED'))
        (cls.eur | cls.gbp | cls.inr | cls.aed).active = True
        cls.company.write({
            'rate_provider': 'frankfurter',
            'rate_currency_ids': [Command.set((cls.eur | cls.gbp | cls.inr | cls.aed).ids)],
        })
        cls.env['res.currency.rate'].search(
            [('currency_id', 'in', (cls.eur | cls.gbp | cls.inr | cls.aed).ids)]).unlink()

    def _rate(self, currency, day=date(2026, 9, 15)):
        return self.env['res.currency.rate'].search(
            [('currency_id', '=', currency.id), ('company_id', '=', self.company.id), ('name', '=', day)])

    def test_update_from_frankfurter_with_backup(self):
        self.company.write({'rate_fallback_provider': 'openexchangerates', 'rate_openexchangerates_key': 'SECRET'})
        with patch(GET, fake_get({'frankfurter': FakeResponse(FRANKFURTER),
                                  'openexchangerates': FakeResponse(OPEN_EXCHANGE_RATES)})):
            self.assertTrue(self.company._update_currency_rates())

        # the source quotes against EUR, the company is in USD
        self.assertAlmostEqual(self._rate(self.eur).company_rate, 1 / 1.1539, places=6)
        self.assertAlmostEqual(self._rate(self.gbp).company_rate, 0.8558 / 1.1539, places=6)
        self.assertEqual(self._rate(self.eur).rate_source, 'Frankfurter')
        # the backup source gives what the main one does not quote
        self.assertAlmostEqual(self._rate(self.aed).company_rate, 3.6725, places=6)
        self.assertEqual(self._rate(self.aed).rate_source, 'Open Exchange Rates')
        self.assertEqual(self.eur.with_company(self.company).with_context(date='2026-09-16').rate,
                         self._rate(self.eur).company_rate)
        self.assertIn('4 rate(s) saved', self.company.rate_last_message)

        # a second update of the same day replaces the rates
        with patch(GET, fake_get({'frankfurter': FakeResponse(dict(FRANKFURTER,
                                                                   rates=dict(FRANKFURTER['rates'], USD=1.2))),
                                  'openexchangerates': FakeResponse(OPEN_EXCHANGE_RATES)})):
            self.company._update_currency_rates()
        self.assertEqual(len(self._rate(self.eur)), 1)
        self.assertAlmostEqual(self._rate(self.eur).company_rate, 1 / 1.2, places=6)

        # changed by hand
        self._rate(self.eur).company_rate = 0.9
        self.assertFalse(self._rate(self.eur).rate_source)

    def test_main_source_fails(self):
        self.company.write({'rate_provider': 'openexchangerates', 'rate_openexchangerates_key': 'SECRET',
                            'rate_fallback_provider': 'ecb'})
        with patch(GET, fake_get({
            'openexchangerates': requests.ConnectionError(
                'https://openexchangerates.org/api/latest.json?app_id=SECRET'),
            'ecb.europa': FakeResponse(content=ECB)})):
            self.company._update_currency_rates()
        self.assertEqual(self._rate(self.gbp, date(2026, 9, 14)).rate_source, 'European Central Bank')
        self.assertNotIn('SECRET', self.company.rate_last_message)
        self.assertIn('could not be reached', self.company.rate_last_message)
        self.assertIn('Not quoted by the sources: AED, INR', self.company.rate_last_message)

    def test_refused_key_and_failure_notification(self):
        self.company.write({'rate_provider': 'openexchangerates', 'rate_openexchangerates_key': 'WRONG',
                            'rate_interval': 'daily'})
        refused = FakeResponse({'error': True, 'status': 401, 'message': 'invalid_app_id',
                                'description': 'Invalid App ID provided.'}, status_code=401)
        self.env.user.group_ids = [Command.link(self.env.ref('account.group_account_manager').id)]
        with patch(GET, fake_get({'openexchangerates': refused})):
            for day in ('2026-09-15', '2026-09-16', '2026-09-17'):
                with freeze_time(day):
                    self.env['res.company']._cron_update_currency_rates()
                self.assertEqual(str(self.company.rate_next_date),
                                 str(date.fromisoformat(day).replace(day=int(day[-2:]) + 1)))
        self.assertEqual(self.company.rate_failure_count, 3)
        self.assertIn('Invalid App ID provided.', self.company.rate_last_message)
        self.assertFalse(self._rate(self.eur))
        self.assertTrue(self.company.rate_next_date)
        notification = self.env['mail.message'].search([('subject', '=', 'Currency rates not updated')])
        self.assertIn(self.env.user.partner_id, notification.partner_ids)

    def test_maximum_change(self):
        self.env['res.currency.rate'].create({
            'currency_id': self.eur.id, 'company_id': self.company.id, 'name': date(2026, 9, 1), 'company_rate': 0.5,
        })
        self.company.rate_max_change = 10.0
        with patch(GET, fake_get({'frankfurter': FakeResponse(FRANKFURTER)})):
            self.company._update_currency_rates()
        self.assertFalse(self._rate(self.eur))
        self.assertTrue(self._rate(self.gbp))
        self.assertIn('changed more than 10.0%: EUR', self.company.rate_last_message)

    def test_exchangerate_api_without_key_and_test_connection(self):
        self.company.rate_provider = 'exchangerate_api'
        data = {'result': 'success', 'time_last_update_unix': 1789430551, 'base_code': 'USD',
                'rates': {'USD': 1, 'EUR': 0.8666, 'GBP': 0.7416, 'INR': 95.96, 'AED': 3.6725}}
        with patch(GET, fake_get({'open.er-api.com': FakeResponse(data)})):
            message = self.company._test_currency_rates()
        self.assertIn('4 rate(s) available', message)
        self.assertFalse(self._rate(self.eur))

        settings = self.env['res.config.settings'].create({})
        with patch(GET, fake_get({'open.er-api.com': FakeResponse(data)})):
            action = settings.action_update_currency_rates()
        self.assertEqual(action['params']['type'], 'success')
        self.assertAlmostEqual(self._rate(self.inr).company_rate, 95.96, places=4)

    def test_nothing_is_fetched_manually(self):
        self.company.rate_interval = 'manual'
        with patch(GET, side_effect=AssertionError('no request expected')):
            self.env['res.company']._cron_update_currency_rates()
