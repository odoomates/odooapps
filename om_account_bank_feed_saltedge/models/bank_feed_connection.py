import logging
import secrets
from datetime import datetime

from odoo import api, fields, models

from odoo.addons.om_account_bank_feed.models.bank_feed_connection import BankFeedError
from .saltedge_api import SaltEdgeAPI

_logger = logging.getLogger(__name__)

CONSENT_SCOPES = ['accounts', 'transactions']
FETCH_SCOPES = ['accounts', 'balance', 'transactions']


def _parse_datetime(value):
    """ :return: a naive UTC datetime from an ISO 8601 value of Salt Edge, or None """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = (parsed - parsed.utcoffset()).replace(tzinfo=None)
    return parsed


class BankFeedConnection(models.Model):
    _inherit = 'bank.feed.connection'

    provider = fields.Selection(selection_add=[('saltedge', 'Salt Edge')], ondelete={'saltedge': 'cascade'})

    # -------------------------------------------------------------------------
    # Client
    # -------------------------------------------------------------------------

    @api.model
    def _saltedge_api(self, company):
        company = company.sudo()
        url = self.env['ir.config_parameter'].sudo().get_str('om_account_bank_feed_saltedge.api_url')
        return SaltEdgeAPI(self.env, company.saltedge_app_id, company.saltedge_secret,
                           private_key=company.saltedge_private_key, url=url)

    def _saltedge_customer_id(self):
        """ :return: the Salt Edge customer of the company, created at the first connection """
        company = self.company_id.sudo()
        if company.saltedge_customer_id:
            return company.saltedge_customer_id
        api = self._saltedge_api(company)
        for _attempt in range(3):
            # a new random identifier: the same database may have been copied, its customer is not ours
            identifier = f'odoo-{company.id}-{secrets.token_hex(8)}'
            try:
                payload = api.request('POST', '/customers', data={'identifier': identifier})
            except BankFeedError as error:
                if getattr(error, 'error_class', '') == 'DuplicatedCustomer':
                    continue
                raise
            data = payload.get('data') or {}
            customer_id = str(data.get('customer_id') or data.get('id') or '')
            if not customer_id:
                raise BankFeedError(self.env._('Salt Edge did not return the customer.'))
            company.write({'saltedge_customer_id': customer_id, 'saltedge_customer_identifier': identifier})
            return customer_id
        raise BankFeedError(self.env._('Salt Edge refused to create the customer.'))

    # -------------------------------------------------------------------------
    # Consent
    # -------------------------------------------------------------------------

    def _saltedge_consent_values(self, return_url):
        from_date = self.sync_start_date or fields.Date.context_today(self).replace(day=1)
        values = {
            'consent': {'scopes': CONSENT_SCOPES, 'from_date': fields.Date.to_string(from_date)},
            'attempt': {
                'fetch_scopes': FETCH_SCOPES,
                'fetch_from_date': fields.Date.to_string(from_date),
                'return_to': return_url,
            },
            'return_connection_id': True,
            'return_error_class': True,
        }
        if self.company_id.sudo().saltedge_include_fake:
            values['provider'] = {'include_sandboxes': True}
        return values

    def _provider_start_consent(self, return_url):
        if self.provider != 'saltedge':
            return super()._provider_start_consent(return_url)
        api = self._saltedge_api(self.company_id)
        payload = api.request('POST', '/connections/connect', data={
            'customer_id': self._saltedge_customer_id(),
            'automatic_refresh': True,
            **self._saltedge_consent_values(return_url),
        })
        return self._saltedge_connect_url(payload)

    def _provider_renew_consent(self, return_url):
        if self.provider != 'saltedge':
            return super()._provider_renew_consent(return_url)
        api = self._saltedge_api(self.company_id)
        payload = api.request('POST', f'/connections/{self.provider_reference}/reconnect',
                              data=self._saltedge_consent_values(return_url))
        return self._saltedge_connect_url(payload)

    def _saltedge_connect_url(self, payload):
        url = (payload.get('data') or {}).get('connect_url')
        if not url:
            raise BankFeedError(self.env._('Salt Edge did not return the page of the bank consent.'))
        return url

    def _provider_handle_callback(self, params):
        if self.provider != 'saltedge':
            return super()._provider_handle_callback(params)
        if params.get('error_class'):
            raise BankFeedError(self.env._(
                'The bank connection was not completed at Salt Edge: %s', params['error_class']))
        connection_id = params.get('connection_id') or self.provider_reference
        if not connection_id:
            raise BankFeedError(self.env._('Salt Edge did not return the connection: connect again.'))
        self.provider_reference = connection_id
        self._saltedge_read_connection()
        return True

    def _saltedge_read_connection(self):
        """ Read the bank, the status and the consent expiry date of the connection """
        api = self._saltedge_api(self.company_id)
        data = api.request('GET', f'/connections/{self.provider_reference}').get('data') or {}
        values = {}
        if data.get('provider_name'):
            values['institution_name'] = data['provider_name']
        consents = api.paginate('/consents', {'connection_id': self.provider_reference})
        active = [consent for consent in consents if consent.get('status', 'active') == 'active']
        if data.get('last_consent_id'):
            active = [consent for consent in active
                      if str(consent.get('id')) == str(data['last_consent_id'])] or active
        expiries = [_parse_datetime(consent.get('expires_at')) for consent in active]
        expiries = [expiry for expiry in expiries if expiry]
        if expiries:
            values['consent_expiry_date'] = max(expiries).date()
        self.write(values)
        if data.get('status') == 'disabled':
            raise BankFeedError(self.env._('Salt Edge disabled this connection: connect the bank again.'))
        if consents and not active:
            raise BankFeedError(self.env._('The consent of the bank has expired or was revoked: renew it.'),
                                expired=True)
        return data

    # -------------------------------------------------------------------------
    # Data
    # -------------------------------------------------------------------------

    def _provider_refresh(self):
        if self.provider != 'saltedge':
            return super()._provider_refresh()
        data = self._saltedge_read_connection()
        next_refresh = _parse_datetime(data.get('next_refresh_possible_at'))
        if data.get('status') != 'active' or (next_refresh and next_refresh > fields.Datetime.now()):
            return True
        try:
            self._saltedge_api(self.company_id).request(
                'POST', f'/connections/{self.provider_reference}/background_refresh',
                data={'attempt': {'fetch_scopes': FETCH_SCOPES}})
        except BankFeedError as error:
            if error.expired:
                raise
            # the data already fetched is read anyway, the new data comes at the next sync
            _logger.info("Salt Edge background refresh of connection %s refused: %s", self.id, error)
        return True

    def _provider_fetch_accounts(self):
        if self.provider != 'saltedge':
            return super()._provider_fetch_accounts()
        records = self._saltedge_api(self.company_id).paginate(
            '/accounts', {'connection_id': self.provider_reference})
        accounts = []
        for record in records:
            extra = record.get('extra') or {}
            balance = record.get('balance')
            accounts.append({
                'ref': str(record['id']),
                'name': record.get('name') or extra.get('account_name') or str(record['id']),
                'account_number': extra.get('iban') or extra.get('account_number') or extra.get('card_number'),
                'currency_code': record.get('currency_code'),
                'balance': float(balance) if balance is not None else None,
                'balance_date': _parse_datetime(record.get('updated_at')),
            })
        return accounts

    def _provider_fetch_transactions(self, feed_account, date_from):
        if self.provider != 'saltedge':
            return super()._provider_fetch_transactions(feed_account, date_from)
        api = self._saltedge_api(self.company_id)
        params = {'connection_id': self.provider_reference, 'account_id': feed_account.provider_account_ref}
        posted_params = dict(params)
        if feed_account.sync_cursor:
            posted_params['from_id'] = feed_account.sync_cursor
        posted = api.paginate('/transactions', posted_params)
        pending = api.paginate('/transactions', {**params, 'pending': 'true'})
        if posted:
            # the identifiers of Salt Edge grow: the next sync reads from the last one
            last_id = max((record['id'] for record in posted), key=lambda value: (len(str(value)), str(value)))
            feed_account.sync_cursor = str(last_id)
        own_number = (feed_account.account_number or '').replace(' ', '')
        transactions = []
        for record, is_pending in [(record, False) for record in posted] + [(record, True) for record in pending]:
            if record.get('duplicated'):
                continue
            transaction = self._saltedge_transaction(record, own_number)
            transaction['pending'] = is_pending or record.get('status') == 'pending'
            if transaction['date'] and transaction['date'] >= date_from:
                transactions.append(transaction)
        return transactions

    def _saltedge_transaction(self, record, own_number):
        extra = record.get('extra') or {}
        amount = float(record.get('amount') or 0.0)
        account_number = (extra.get('account_number') or '').replace(' ', '')
        description = record.get('description') or extra.get('information') or extra.get('additional') or ''
        return {
            'id': str(record['id']),
            'date': fields.Date.to_date(record.get('made_on')),
            'amount': amount,
            'currency_code': record.get('currency_code'),
            'payment_ref': description,
            'ref': extra.get('id') or extra.get('record_number'),
            'partner_name': extra.get('payee') if amount < 0 else extra.get('payer'),
            'account_number': account_number if account_number and account_number != own_number else False,
            'transaction_type': record.get('category') if record.get('category') != 'uncategorized' else False,
            'foreign_currency_code': extra.get('original_currency_code'),
            'amount_currency': extra.get('original_amount'),
            'raw': record,
        }

    def _provider_disconnect(self):
        if self.provider != 'saltedge':
            return super()._provider_disconnect()
        try:
            self._saltedge_api(self.company_id).request('DELETE', f'/connections/{self.provider_reference}')
        except BankFeedError as error:
            if getattr(error, 'error_class', '') != 'ConnectionNotFound':
                raise
        return True
