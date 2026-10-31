import json
import os
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

import requests
from freezegun import freeze_time

from odoo import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.om_currency_rate_update.models.rate_providers import CENTRAL_BANKS

from .test_rate_update import GET, FakeResponse, fake_get

LOGGER = 'odoo.addons.om_currency_rate_update.models.res_company'
POST = GET.replace('requests.get', 'requests.post')
USD_INR, USD_SAR, USD_AED = 95.2492, 3.75, 3.6725


def fixture(name):
    """ A response recorded from the bank, trimmed """
    with open(os.path.join(os.path.dirname(__file__), 'data', name), 'rb') as file:
        return file.read()


def answer(name):
    """ The recorded response `name` as answered by the bank, JSON or not """
    content = fixture(name)
    return FakeResponse(json.loads(content)) if name.endswith('.json') else FakeResponse(content=content)


@tagged('post_install', '-at_install')
class TestCentralBank(AccountTestInvoicingCommon):
    """ The Central Bank source, with the recorded responses of each bank; the company is in USD """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Currency = cls.env['res.currency'].with_context(active_test=False)
        cls.eur, cls.inr, cls.aed, cls.jpy, cls.idr, cls.sar, cls.irr = (
            Currency.search([('name', '=', code)]) for code in ('EUR', 'INR', 'AED', 'JPY', 'IDR', 'SAR', 'IRR'))
        currencies = cls.eur | cls.inr | cls.aed | cls.jpy | cls.idr | cls.sar | cls.irr
        currencies.active = True
        cls.env['res.currency.rate'].search([('currency_id', 'in', currencies.ids)]).unlink()
        # the readers are checked, not the held-back changes against the rates of other tests or of the demo data
        cls.company.write({'rate_provider': 'frankfurter', 'rate_currency_ids': [Command.set(currencies.ids)],
                           'rate_max_change': 0})

    def _rate(self, currency, day):
        return self.env['res.currency.rate'].search(
            [('currency_id', '=', currency.id), ('company_id', '=', self.company.id), ('name', '=', day)])

    def _country(self, code):
        # by code: the United Kingdom is base.uk
        return self.env['res.country'].search([('code', '=', code)])

    def _use_bank_of(self, country_code):
        self.company.write({'country_id': self._country(country_code).id, 'rate_central_bank': False})
        self.company.rate_provider = 'central_bank'

    def _assert_rate(self, currency, day, rate, source):
        record = self._rate(currency, day)
        self.assertAlmostEqual(record.company_rate, rate, places=6)
        self.assertEqual(record.rate_source, source)

    @contextmanager
    def _answers(self, get, post=None):
        """ The banks answer by host, from the recorded responses; `get` and `post` may be functions """
        with patch(GET, side_effect=get if callable(get) else fake_get(get)), \
                patch(POST, side_effect=post if callable(post) else fake_get(post or {})):
            yield

    def _check_bank(self, country, code, answers, day, quotes, missing=()):
        """ Update from the bank of `country` and check the rates saved.

        :param quotes: {currency code: units of the home currency per 1 unit, as published by the bank}, with USD
        :param missing: the currencies the bank gives no usable rate for
        """
        self._use_bank_of(country)
        self.assertEqual(self.company.rate_central_bank, code)
        bank = CENTRAL_BANKS[code]
        Currency = self.env['res.currency'].with_context(active_test=False)
        currencies = {name: Currency.search([('name', '=', name)])
                      for name in (bank.home_currency, *quotes, *missing) if name != 'USD'}
        self.assertTrue(all(currencies.values()), currencies)
        records = Currency.browse([currency.id for currency in currencies.values()])
        records.active = True
        self.company.rate_currency_ids = records
        with answers:
            self.assertTrue(self.company._update_currency_rates(), self.company.rate_last_message)
        # the company is in USD: 1 USD = quotes['USD'] home currency
        self._assert_rate(currencies[bank.home_currency], day, quotes['USD'], bank.name)
        for name, quote in quotes.items():
            if name != 'USD':
                self._assert_rate(currencies[name], day, quotes['USD'] / quote, bank.name)
        for name in missing:
            self.assertFalse(self._rate(currencies[name], day), name)
        self.assertIn('%s rate(s) saved for %s' % (len(quotes), day), self.company.rate_last_message)
        self.assertIn('From %s' % bank.name, self.company.rate_last_message)

    def test_rbi(self):
        self._use_bank_of('IN')
        self.assertEqual(self.company.rate_central_bank, 'rbi')
        posted = {}

        def post(url, data=None, **kwargs):
            posted.update(data)
            return FakeResponse(content=fixture('rbi_rates.html'))
        with patch(GET, fake_get({'rbi.org.in': FakeResponse(content=fixture('rbi_form.html'))})), \
                patch(POST, side_effect=post):
            self.assertTrue(self.company._update_currency_rates())
        # the form is posted back with its hidden fields
        self.assertEqual(posted['__VIEWSTATEGENERATOR'], '6A117BB1')
        self.assertTrue(posted['txtFromDate'] and posted['txtToDate'])

        bank, day = 'Reserve Bank of India (FBIL reference rates)', date(2026, 10, 30)
        # the newest day of the table, "INR / 1 USD" inverted and converted to the USD of the company
        self._assert_rate(self.inr, day, USD_INR, bank)
        self._assert_rate(self.eur, day, USD_INR / 106.5451, bank)
        # quoted per 100 JPY and per 10000 IDR
        self._assert_rate(self.jpy, day, USD_INR / (60.45 / 100), bank)
        self._assert_rate(self.idr, day, USD_INR / (52.4427 / 10000), bank)
        self._assert_rate(self.aed, day, USD_INR / 25.9332, bank)
        self.assertIn('5 rate(s) saved for 2026-10-30', self.company.rate_last_message)
        self.assertIn('From %s' % bank, self.company.rate_last_message)
        self.assertIn('Not quoted by the sources: IRR, SAR', self.company.rate_last_message)

    def test_sama_with_missing_intermediate_certificate(self):
        self._use_bank_of('SA')
        self.assertEqual(self.company.rate_central_bank, 'sama')
        calls = []

        def get(url, verify=True, headers=None, **kwargs):
            calls.append(verify)
            self.assertNotIn('python-requests', str(headers))
            if verify is True:
                raise requests.exceptions.SSLError('unable to get local issuer certificate')
            return FakeResponse(json.loads(fixture('sama_rates.json')))
        with patch(GET, side_effect=get):
            self.company._update_currency_rates()
        # retried with the trusted certificates and the intermediate one
        with open(calls[1]) as bundle:
            self.assertIn('-----BEGIN CERTIFICATE-----', bundle.read())

        bank, day = 'Saudi Central Bank (SAMA)', date(2026, 10, 31)
        self._assert_rate(self.sar, day, USD_SAR, bank)
        self._assert_rate(self.eur, day, USD_SAR / 4.18612, bank)
        self._assert_rate(self.jpy, day, USD_SAR / 0.02381, bank)
        self._assert_rate(self.inr, day, USD_SAR / 0.03949, bank)
        self._assert_rate(self.aed, day, USD_SAR / 1.02096, bank)
        # 0.0002 SAR for 1 IDR is too rough, the rates of the day before are not used
        self.assertFalse(self._rate(self.idr, day))
        self.assertIn('Not quoted by the sources: IDR, IRR', self.company.rate_last_message)

    def test_cbuae(self):
        self._use_bank_of('AE')
        self.assertEqual(self.company.rate_central_bank, 'cbuae')
        with patch(GET, fake_get({'centralbank.ae': FakeResponse(content=fixture('cbuae_rates.html'))})):
            self.company._update_currency_rates()

        bank, day = 'Central Bank of the UAE', date(2026, 10, 30)
        self._assert_rate(self.aed, day, USD_AED, bank)
        self._assert_rate(self.eur, day, USD_AED / 4.092378, bank)
        self._assert_rate(self.jpy, day, USD_AED / 0.02334, bank)
        self._assert_rate(self.sar, day, USD_AED / 0.978524, bank)
        # 2E-06 AED for 1 IRR is too rough
        self.assertFalse(self._rate(self.irr, day))
        self.assertIn('Not quoted by the sources: IDR, IRR', self.company.rate_last_message)

    # Middle East

    def test_cbo(self):
        # the mid of the buying and selling rates, 7 decimals: 0.0000231 OMR for 1 IDR still has 3 digits
        self._check_bank('OM', 'cbo', self._answers({'cbo.gov.om': answer('cbo_rates.html')}),
                         date(2026, 10, 29), {
                             'USD': (0.384 + 0.385) / 2, 'EUR': (0.4278528 + 0.4290055) / 2,
                             'JPY': (0.0024341 + 0.0024406) / 2, 'AED': (0.1045438 + 0.1048218) / 2,
                             'IDR': (0.0000231 + 0.0000232) / 2,
                         })

    def test_cbk_kuwait(self):
        # in fils, 1/1000 KWD; 0.017 fils for 1 IDR is too rough
        self._check_bank('KW', 'cbk_kuwait', self._answers({
            'cbk.gov.kw': answer('cbk_kuwait_rates.html')}), date(2026, 10, 29), {
                'USD': 308.250 / 1000, 'EUR': 343.529 / 1000, 'JPY': 1.9538 / 1000,
            }, missing=['IDR'])

    def test_cbb(self):
        self._check_bank('BH', 'cbb', self._answers({'cbb.gov.bh': answer('cbb_rates.html')}),
                         date(2026, 10, 29), {'USD': 0.376081, 'EUR': 0.418936, 'JPY': 0.002381, 'SAR': 0.100224},
                         missing=['IDR'])

    def test_cbj(self):
        # the newest of the days, in fils, the yen per 100, the mid of the lowest and highest rates
        self._check_bank('JO', 'cbj', self._answers({'cbj.gov.jo': answer('cbj_rates.html')}),
                         date(2026, 10, 29), {
                             'USD': (708 + 710) / 2 / 1000, 'EUR': (787.58 + 792.43) / 2 / 1000,
                             'JPY': (447.93 + 450.56) / 2 / 100 / 1000,
                         })

    def test_boi(self):
        # 0.0003 ILS for 10 LBP is too rough
        self._check_bank('IL', 'boi', self._answers({'boi.org.il': answer('boi_rates.json')}),
                         date(2026, 10, 30), {'USD': 3.118, 'EUR': 3.4932, 'JPY': 1.9822 / 100}, missing=['LBP'])

    # Africa and South Asia

    def test_bangladesh_bank(self):
        # the weighted average rate of the US dollar, the mid of the cross rates; the Sri Lankan rupee is quoted
        # per 1 BDT (2.68 LKR), not in BDT
        self._check_bank('BD', 'bangladesh_bank', self._answers({
            'bb.org.bd': answer('bb_rates.html')}), date(2026, 10, 29), {
                'USD': 123.99, 'EUR': (138.2736 + 138.3232) / 2, 'JPY': (0.7855 + 0.7856) / 2,
                'INR': (1.3017 + 1.3021) / 2, 'LKR': 1 / ((2.6809 + 2.6825) / 2),
            })

    def test_cbn(self):
        # the central rates of the newest day; the CFA franc is not taken
        self._check_bank('NG', 'cbn', self._answers({'cbn.gov.ng': answer('cbn_rates.json')}),
                         date(2026, 10, 30), {'USD': 1345.7565, 'EUR': 1502.6717, 'JPY': 8.5543, 'SAR': 358.5815},
                         missing=['XOF'])

    def test_cbk_kenya(self):
        posted = {}

        def post(url, params=None, data=None, **kwargs):
            posted.update(params, **data)
            return answer('cbk_kenya_rates.json')
        # the newest day, the yen per 100, the Ugandan shilling quoted per 1 KES
        self._check_bank('KE', 'cbk_kenya', self._answers({}, post), date(2026, 10, 30), {
            'USD': 129.95, 'EUR': 144.74, 'JPY': 82.31 / 100, 'SAR': 34.62, 'UGX': 1 / 33.43,
        })
        # the table of the indicative rates, newest first
        self.assertEqual((posted['table_id'], posted['order[0][dir]']), (193, 'desc'))

    @freeze_time('2026-10-31')
    def test_cbsl(self):
        posted = {}

        def post(url, data=None, **kwargs):
            posted.update({key: [value for name, value in data if name == key] for key, value in data})
            return answer('cbsl_rates.html')
        self._check_bank('LK', 'cbsl', self._answers({
            'exrates.php': answer('cbsl_form.html')}, post), date(2026, 10, 30), {
                'USD': 332.6106, 'EUR': 372.4241, 'JPY': 2.1121,
            })
        # every currency of the form, for the last days
        self.assertEqual(posted['chk_cur[]'], ['EUR~Euro', 'JPY~Japanese Yen', 'USD~US Dollar'])
        self.assertEqual((posted['txtStart'], posted['txtEnd']), (['2026-10-21'], ['2026-10-31']))

    # Europe and Central Asia

    def test_tcmb(self):
        # the mid of the forex buying and selling rates, the yen per 100
        self._check_bank('TR', 'tcmb', self._answers({'tcmb.gov.tr': answer('tcmb_rates.xml')}),
                         date(2026, 10, 30), {
                             'USD': (49.7747 + 49.8644) / 2, 'EUR': (55.7149 + 55.8153) / 2,
                             'JPY': (31.5605 + 31.7695) / 2 / 100,
                         })

    def test_nbp(self):
        self._check_bank('PL', 'nbp', self._answers({'api.nbp.pl': answer('nbp_rates.json')}),
                         date(2026, 10, 30), {'USD': 3.9251, 'EUR': 4.3955, 'JPY': 0.024953, 'HUF': 0.012017})

    def test_cnb(self):
        self._check_bank('CZ', 'cnb', self._answers({'cnb.cz': answer('cnb_rates.txt')}),
                         date(2026, 10, 30), {
                             'USD': 21.814, 'EUR': 24.360, 'JPY': 13.875 / 100, 'IDR': 1.204 / 1000,
                         })

    def test_bnr(self):
        self._check_bank('RO', 'bnr', self._answers({'bnr.ro': answer('bnr_rates.xml')}),
                         date(2026, 10, 30), {'USD': 4.7698, 'EUR': 5.3426, 'JPY': 3.0317 / 100})

    def test_mnb(self):
        self._check_bank('HU', 'mnb', self._answers({'mnb.hu': answer('mnb_rates.html')}),
                         date(2026, 10, 30), {
                             'USD': 326.64, 'EUR': 365.80, 'JPY': 207.67 / 100, 'IDR': 1.80 / 100,
                         })

    def test_nbu(self):
        # the rates are set for the next working day, and saved under it
        self._check_bank('UA', 'nbu', self._answers({
            'bank.gov.ua': answer('nbu_rates.json')}), date(2026, 11, 2), {
                'USD': 45.3526, 'EUR': 50.6843, 'JPY': 0.28855,
            })

    def test_nbg(self):
        self._check_bank('GE', 'nbg', self._answers({'nbg.gov.ge': answer('nbg_rates.json')}),
                         date(2026, 10, 31), {
                             'USD': 2.5992, 'EUR': 2.9116, 'JPY': 1.6521 / 100, 'AED': 7.0765 / 10,
                         })

    def test_nbk(self):
        self._check_bank('KZ', 'nbk', self._answers({
            'nationalbank.kz': answer('nbk_rates.xml')}), date(2026, 10, 31), {
                'USD': 453.87, 'EUR': 508.33, 'JPY': 2.89, 'IDR': 25.05 / 1000,
            })


    def test_boe(self):
        # units of each currency per 1 GBP, the newest day; no rate of the rouble since 2022
        self._check_bank('GB', 'boe', self._answers({'bankofengland.co.uk': answer('boe_rates.csv')}),
                         date(2026, 10, 29), {'USD': 1 / 1.3375, 'EUR': 1 / 1.1979, 'JPY': 1 / 211.083},
                         missing=['RUB'])

    def test_snb(self):
        # the newest day of the feed, the yen per 100
        self._check_bank('CH', 'snb', self._answers({'snb.ch': answer('snb_rates.xml')}), date(2026, 10, 30), {
            'USD': 0.8212, 'EUR': 0.9196, 'GBP': 1.1028, 'JPY': 0.5222 / 100,
        })

    def test_norges_bank(self):
        # the multipliers of the series (per 100 JPY and IDR); the rouble stopped in 2022, the index is skipped
        self._check_bank('NO', 'norges_bank', self._answers({
            'norges-bank.no': answer('norges_bank_rates.json')}), date(2026, 10, 30), {
                'USD': 9.2302, 'EUR': 10.312, 'JPY': 5.8698 / 100, 'IDR': 0.05086 / 100,
            }, missing=['RUB'])

    def test_riksbank(self):
        # 0.00054 SEK for 1 IDR is too rough; the series of the Deutsche Mark stopped in 2002
        self._check_bank('SE', 'riksbank', self._answers({'riksbank.se': answer('riksbank_rates.json')}),
                         date(2026, 10, 30), {'USD': 9.82635, 'EUR': 10.978, 'JPY': 0.06249, 'KRW': 0.00736},
                         missing=['IDR'])

    def test_danmarks_nationalbank(self):
        # DKK per 100 units
        self._check_bank('DK', 'danmarks_nationalbank', self._answers({
            'nationalbanken.dk': answer('danmarks_nationalbank_rates.xml')}), date(2026, 10, 30), {
                'USD': 668.95 / 100, 'EUR': 747.35 / 100, 'JPY': 4.254 / 100, 'IDR': 0.0369 / 100,
            })

    @freeze_time('2026-10-31')
    def test_sedlabanki(self):
        asked = {}

        def get(url, params=None, **kwargs):
            asked.update(params)
            return answer('sedlabanki_rates.xml')
        # the mid rates of the newest day, the buying rates are empty
        self._check_bank('IS', 'sedlabanki', self._answers(get), date(2026, 10, 30), {
            'USD': 121.73, 'EUR': 136.0, 'JPY': 0.7741})
        # the official reference rates of the last days
        self.assertEqual((asked['GroupID'], asked['DagsFra'], asked['DagsTil']), (9, '2026-10-21', '2026-10-31'))

    def test_cba(self):
        posted = {}

        def post(url, data=None, headers=None, **kwargs):
            posted.update(data=data, action=headers.get('SOAPAction'))
            return answer('cba_rates.xml')
        # AMD per amount: per 10 JPY, per 100 IRR
        self._check_bank('AM', 'cba', self._answers({}, post), date(2026, 10, 30), {
            'USD': 360.14, 'EUR': 403.36, 'JPY': 22.913 / 10, 'IRR': 0.019357 / 100,
        })
        self.assertIn(b'<ExchangeRatesLatest', posted['data'])
        self.assertEqual(posted['action'], '"http://www.cba.am/ExchangeRatesLatest"')

    def test_nbrb(self):
        # BYN per scale, saved under the day the rates apply from
        self._check_bank('BY', 'nbrb', self._answers({'nbrb.by': answer('nbrb_rates.json')}), date(2026, 10, 31), {
            'USD': 2.9462, 'EUR': 3.2801, 'JPY': 1.8651 / 100, 'IRR': 0.158 / 100000,
        })

    # Americas and Asia-Pacific

    def test_boc(self):
        # 0.000077 CAD for 1 IDR is too rough; the SAR is no longer published, its last rate is not taken
        self._check_bank('CA', 'boc', self._answers({
            'bankofcanada.ca': answer('boc_rates.json')}), date(2026, 10, 30), {
                'USD': 1.3960, 'EUR': 1.5582, 'JPY': 0.008870,
            }, missing=['IDR', 'SAR'])

    @freeze_time('2026-11-01')
    def test_bcb(self):
        # no file for the weekend: the one of Friday, the mid of the buying and selling rates
        self._check_bank('BR', 'bcb', self._answers({
            '20261030.csv': answer('bcb_rates.csv'),
            'bcb.gov.br': FakeResponse(status_code=404),
        }), date(2026, 10, 30), {
            'USD': (5.4206 + 5.4212) / 2, 'EUR': (6.0505 + 6.0522) / 2, 'JPY': (0.03442 + 0.03443) / 2,
        })

    def test_bnm(self):
        self._check_bank('MY', 'bnm', self._answers({'bnm.gov.my': answer('bnm_rates.json')}),
                         date(2026, 10, 30), {
                             'USD': 4.0565, 'EUR': 4.5415, 'JPY': 2.5791 / 100, 'IDR': 0.0224 / 100,
                         })

    def test_bsp(self):
        # the day of the bulletin in Manila; 0.0035 PHP for 1 IDR is too rough, no rate for KWD
        self._check_bank('PH', 'bsp', self._answers({'bsp.gov.ph': answer('bsp_rates.json')}),
                         date(2026, 10, 30), {'USD': 63.8520, 'EUR': 71.3865, 'JPY': 0.4050},
                         missing=['IDR', 'KWD'])

    def test_rba(self):
        def get(url, headers=None, **kwargs):
            # the firewall of the RBA refuses the user agent of the other banks
            self.assertNotIn('User-Agent', headers or {})
            return answer('rba_rates.xml')
        # units of each currency per 1 AUD; the trade-weighted index is skipped
        self._check_bank('AU', 'rba', self._answers(get), date(2026, 10, 30), {
            'USD': 1 / 0.7040, 'EUR': 1 / 0.6293, 'JPY': 1 / 110.82, 'IDR': 1 / 12780,
        })

    @freeze_time('2026-11-03')
    def test_mas(self):
        posted = {}

        def post(url, data=None, **kwargs):
            posted.update(data)
            return answer('mas_rates.html')
        # the newest day of the table, per 100 IDR and JPY
        self._check_bank('SG', 'mas', self._answers({'mas.gov.sg': answer('mas_form.html')}, post),
                         date(2026, 10, 30), {
                             'USD': 1.2779, 'EUR': 1.4301, 'IDR': 0.007044 / 100, 'JPY': 0.8119 / 100,
                         })
        # the form posted back with its hidden fields and every currency, daily, from the month of 10 days ago
        field = 'ctl00$ContentPlaceHolder1$%s'
        self.assertTrue(posted['__VIEWSTATE'])
        self.assertEqual(posted[field % 'EndOfPeriodPer100UnitsCheckBoxList$0'], 'on')
        self.assertEqual((posted[field % 'StartMonthDropDownList'], posted[field % 'EndMonthDropDownList'],
                          posted[field % 'FrequencyDropDownList']), (10, 11, 'D'))

    def test_banrep(self):
        # the TRM, saved under the day it applies from
        self._check_bank('CO', 'banrep', self._answers({'datos.gov.co': answer('banrep_rates.json')}),
                         date(2026, 10, 31), {'USD': 3182.99})

    def test_bcra(self):
        # the dong per 1000, the old code of the Mexican peso; the reference rate REF is not a currency
        self._check_bank('AR', 'bcra', self._answers({'bcra.gob.ar': answer('bcra_rates.json')}),
                         date(2026, 10, 30), {
                             'USD': 1534.0, 'EUR': 1710.8702, 'JPY': 9.742775, 'MXN': 81.598349,
                             'VND': 59.450451 / 1000,
                         })

    @mute_logger(LOGGER)
    def test_no_rates_published(self):
        """ The answers of the banks for days without rates, and a refused request """
        for country, responses, error in (
            ('IN', {GET: fake_get({'rbi.org.in': FakeResponse(content=fixture('rbi_form.html'))}),
                    POST: fake_get({'rbi.org.in': FakeResponse(content=fixture('rbi_empty.html'))})},
             'Reserve Bank of India (FBIL reference rates) answered without rates.'),
            ('SA', {GET: fake_get({'sama.gov.sa': FakeResponse(json.loads(fixture('sama_empty.json')))})},
             'Saudi Central Bank (SAMA) answered without rates.'),
            ('AE', {GET: fake_get({'centralbank.ae': FakeResponse(content=fixture('cbuae_empty.html'))})},
             'Central Bank of the UAE answered without rates.'),
            ('AE', {GET: fake_get({'centralbank.ae': FakeResponse(content=b'Forbidden', status_code=403)})},
             'Central Bank of the UAE could not be reached: HTTP 403'),
            ('LK', {GET: fake_get({'cbsl.gov.lk': answer('cbsl_form.html')}),
                    POST: fake_get({'cbsl.gov.lk': answer('cbsl_empty.html')})},
             'Central Bank of Sri Lanka answered without rates.'),
            ('KE', {GET: fake_get({}), POST: fake_get({'centralbank.go.ke': answer('cbk_kenya_empty.json')})},
             'Central Bank of Kenya answered without rates.'),
            ('NG', {GET: fake_get({'cbn.gov.ng': answer('cbn_empty.json')})},
             'Central Bank of Nigeria answered without rates.'),
            # no file for a week
            ('BR', {GET: fake_get({'bcb.gov.br': FakeResponse(status_code=404)})},
             'Banco Central do Brasil (PTAX) answered without rates.'),
            # the firewall of the bank
            ('PH', {GET: fake_get({'bsp.gov.ph': FakeResponse(content=fixture('bsp_refused.html'), status_code=403)})},
             'Bangko Sentral ng Pilipinas could not be reached: HTTP 403'),
            # the header alone, before the first rates of the period
            ('GB', {GET: fake_get({'bankofengland.co.uk': FakeResponse(content=b'DATE,XUDLUSS\r\n')})},
             'Bank of England answered without rates.'),
            ('SE', {GET: fake_get({'riksbank.se': FakeResponse([])})}, 'Sveriges Riksbank answered without rates.'),
            ('CO', {GET: fake_get({'datos.gov.co': FakeResponse([])})},
             'Banco de la República (TRM) answered without rates.'),
            ('NO', {GET: fake_get({'norges-bank.no': FakeResponse({'data': {}})})},
             'Norges Bank answered without rates.'),
        ):
            self._use_bank_of(country)
            with patch(GET, side_effect=responses[GET]), patch(POST, side_effect=responses.get(POST)):
                self.assertFalse(self.company._update_currency_rates())
            self.assertIn(error, self.company.rate_last_message)
        self.assertFalse(self.env['res.currency.rate'].search([('rate_source', '!=', False)]))

    @mute_logger(LOGGER)
    def test_no_bank(self):
        # no bank in Belgium: an error until one is chosen
        self._use_bank_of('BE')
        self.assertFalse(self.company.rate_central_bank)
        with patch(GET, side_effect=AssertionError('no request expected')):
            self.assertFalse(self.company._update_currency_rates())
        self.assertIn('Choose the central bank', self.company.rate_last_message)

        # the settings give the bank of the country when the source is chosen, as main or backup source
        self.company.write({'country_id': self.env.ref('base.sa').id, 'rate_provider': 'frankfurter'})
        settings = self.env['res.config.settings'].new({'rate_fallback_provider': 'central_bank'})
        settings._onchange_rate_central_bank()
        self.assertEqual(settings.rate_central_bank, 'sama')
        # a bank chosen is kept
        self.company.write({'rate_central_bank': 'cbuae', 'rate_provider': 'central_bank'})
        self.assertEqual(self.company.rate_central_bank, 'cbuae')

    def test_bank_of_the_country(self):
        for country, bank in (('OM', 'cbo'), ('KW', 'cbk_kuwait'), ('KE', 'cbk_kenya'), ('TR', 'tcmb'), ('PL', 'nbp'),
                              ('BR', 'bcb'), ('CA', 'boc'), ('PH', 'bsp'), ('GB', 'boe'), ('CH', 'snb'),
                              ('IS', 'sedlabanki'), ('CO', 'banrep'), ('AR', 'bcra')):
            self._use_bank_of(country)
            self.assertEqual(self.company.rate_central_bank, bank, country)
        # one bank by country, in the currency of the country
        self.assertEqual(len({bank.country for bank in CENTRAL_BANKS.values()}), len(CENTRAL_BANKS))
        for bank in CENTRAL_BANKS.values():
            self.assertEqual(self._country(bank.country).currency_id.name, bank.home_currency, bank.code)
