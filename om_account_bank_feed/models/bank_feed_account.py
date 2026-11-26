import math
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import format_amount
from odoo.tools.sql import escape_like_value
from odoo.addons.base.models.res_partner_bank import sanitize_account_number

# the days read again before the last transaction, for the transactions the bank books late
SYNC_OVERLAP_DAYS = 15


def _default_sync_start_date(self):
    return fields.Date.context_today(self).replace(day=1)


class BankFeedAccount(models.Model):
    _name = 'bank.feed.account'
    _description = 'Bank Feed Account'
    _order = 'connection_id, name, id'
    _check_company_auto = True

    connection_id = fields.Many2one(
        'bank.feed.connection', string='Connection', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='connection_id.company_id', store=True, index=True)
    provider_account_ref = fields.Char(string='Provider Account ID', required=True, readonly=True)
    name = fields.Char(string='Account Name', required=True)
    account_number = fields.Char(string='IBAN / Number')
    currency_code = fields.Char(string='Currency Code', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    balance = fields.Monetary(string='Bank Balance', currency_field='currency_id', readonly=True)
    has_balance = fields.Boolean(readonly=True)
    balance_date = fields.Datetime(string='Balance Date', readonly=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', check_company=True, index='btree_not_null',
        domain="[('type', 'in', ('bank', 'credit'))]",
        help="The bank journal receiving the transactions of this account.")
    sync_start_date = fields.Date(
        string='Sync From', required=True, default=_default_sync_start_date,
        help="The first sync imports the transactions from this date.")
    last_sync = fields.Datetime(string='Last Sync', readonly=True, copy=False)
    sync_cursor = fields.Char(
        readonly=True, copy=False,
        help="Where the provider continues reading the transactions at the next sync.")
    journal_balance = fields.Monetary(string='Journal Balance', currency_field='currency_id', readonly=True)
    balance_difference = fields.Monetary(
        string='Difference', currency_field='currency_id', readonly=True,
        help="The balance of the bank minus the balance of the transactions of the journal, at the last sync.")
    balance_mismatch = fields.Boolean(string='Balance Mismatch', readonly=True)

    _journal_uniq = models.Constraint(
        'UNIQUE(journal_id)',
        'A journal receives the transactions of one bank account only.',
    )
    _ref_uniq = models.Constraint(
        'UNIQUE(connection_id, provider_account_ref)',
        'The bank account is already in the connection.',
    )

    @api.depends('name', 'account_number')
    def _compute_display_name(self):
        for account in self:
            account.display_name = (f'{account.name} ({account.account_number})'
                                    if account.account_number and account.account_number != account.name
                                    else account.name)

    @api.constrains('journal_id', 'currency_id')
    def _check_journal_currency(self):
        for account in self.filtered(lambda acc: acc.journal_id and acc.currency_id):
            journal_currency = account.journal_id.currency_id or account.journal_id.company_id.currency_id
            if journal_currency != account.currency_id:
                raise ValidationError(self.env._(
                    'The bank account %(account)s is in %(currency)s: map it to a journal in %(currency)s, not '
                    'to %(journal)s in %(journal_currency)s.',
                    account=account.display_name, currency=account.currency_id.name,
                    journal=account.journal_id.display_name, journal_currency=journal_currency.name,
                ))

    def write(self, vals):
        if 'journal_id' in vals or 'sync_start_date' in vals:
            # a new journal or start date reads the transactions from the sync start date again
            vals = {**vals, 'sync_cursor': False, 'last_sync': False}
        return super().write(vals)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_create_journal(self):
        """ Create a bank journal for this account, with its number and currency """
        self.ensure_one()
        self.connection_id._check_manager()
        if self.journal_id:
            return False
        if self.currency_code and not self.currency_id.active:
            raise UserError(self.env._(
                'The bank account %(account)s is in %(currency)s: activate that currency first.',
                account=self.display_name, currency=self.currency_code))
        company = self.company_id
        currency = self.currency_id if self.currency_id and self.currency_id != company.currency_id else False
        journal = self.env['account.journal'].create({
            'name': self.name if not self.account_number else f'{self.name} {self.account_number[-4:]}',
            'type': 'bank',
            'company_id': company.id,
            'currency_id': currency.id if currency else False,
            'bank_statements_source': 'bank_feed',
            'bank_account_id': self._find_or_create_company_bank_account().id,
        })
        self.journal_id = journal
        return True

    def _find_or_create_company_bank_account(self):
        """ :return: the bank account of the company with the number of this account, created if needed """
        PartnerBank = self.env['res.partner.bank']
        sanitized = sanitize_account_number(self.account_number or '')
        if not sanitized:
            return PartnerBank
        partner = self.company_id.partner_id
        bank_account = PartnerBank.search([
            ('sanitized_account_number', '=', sanitized), ('partner_id', '=', partner.id),
        ], limit=1)
        return bank_account or PartnerBank.create({
            'account_number': self.account_number,
            'partner_id': partner.id,
        })

    def action_sync(self):
        return self.connection_id.action_sync()

    def action_open_journal(self):
        self.ensure_one()
        return self.journal_id.open_action()

    # -------------------------------------------------------------------------
    # Sync
    # -------------------------------------------------------------------------

    def _get_sync_date_from(self):
        """ :return: the first date to read: the sync start date at the first sync, then a few days before
        the last transaction imported, for the transactions the bank books late """
        self.ensure_one()
        last = self.env['account.bank.statement.line'].sudo().search(
            [('bank_feed_account_id', '=', self.id), ('bank_feed_pending', '=', False)],
            order='date desc', limit=1)
        if not last:
            return self.sync_start_date
        return max(self.sync_start_date, last.date - timedelta(days=SYNC_OVERLAP_DAYS))

    def _sync_transactions(self):
        """ Import the new transactions of the account in its journal.

        :return: the number of statement lines created
        """
        self.ensure_one()
        connection = self.connection_id
        journal = self.journal_id
        date_from = self._get_sync_date_from()
        transactions = [
            transaction for transaction in connection._provider_fetch_transactions(self, date_from)
            if transaction['date'] >= self.sync_start_date and transaction.get('id')
        ]
        Line = self.env['account.bank.statement.line'].sudo().with_company(journal.company_id)
        ids = [str(transaction['id']) for transaction in transactions]
        existing = {
            line.bank_feed_transaction_id: line for line in Line.search([
                ('journal_id', '=', journal.id), ('bank_feed_transaction_id', 'in', ids),
            ])
        } if ids else {}

        to_create = []
        to_replace = Line
        skipped = pending = 0
        currencies = self._get_foreign_currencies(transactions)
        for transaction in transactions:
            transaction_id = str(transaction['id'])
            is_pending = bool(transaction.get('pending'))
            if is_pending and not connection.include_pending:
                pending += 1
                continue
            line = existing.get(transaction_id)
            if line:
                if line.bank_feed_pending and not is_pending:
                    if line.is_reconciled:
                        line.bank_feed_pending = False
                        skipped += 1
                        continue
                    to_replace |= line
                else:
                    skipped += 1
                    continue
            if not transaction['amount']:
                skipped += 1
                continue
            to_create.append(self._statement_line_values(transaction, is_pending, currencies))
            pending += is_pending

        removed = 0
        if connection.include_pending:
            # the pending transactions the bank no longer reports were dropped or booked under another id
            stale = Line.search([
                ('bank_feed_account_id', '=', self.id),
                ('bank_feed_pending', '=', True),
                ('date', '>=', date_from),
                ('bank_feed_transaction_id', 'not in', ids),
            ]).filtered(lambda line: not line.is_reconciled)
            removed = len(stale)
            to_replace |= stale
        if to_replace:
            to_replace.unlink()

        to_create.sort(key=lambda values: (values['date'], values['bank_feed_transaction_id']))
        self._set_partners(to_create)
        lines = Line.create(to_create) if to_create else Line
        self.last_sync = fields.Datetime.now()
        message = self._check_balance()
        level = 'warning' if self.balance_mismatch else 'info'
        if removed:
            message = '\n'.join(filter(None, [
                self.env._('%s pending transaction(s) no longer reported by the bank were removed.', removed),
                message,
            ]))
        connection._log(
            level, message or self.env._('Sync done.'), account=self,
            imported_count=len(lines), skipped_count=skipped, pending_count=pending, date_from=date_from,
        )
        return len(lines)

    def _statement_line_values(self, transaction, is_pending, currencies):
        journal = self.journal_id
        currency = journal.currency_id or journal.company_id.currency_id
        values = {
            'journal_id': journal.id,
            'date': transaction['date'],
            'payment_ref': transaction.get('payment_ref') or transaction.get('ref') or '/',
            'amount': currency.round(transaction['amount']),
            'partner_name': transaction.get('partner_name') or False,
            'account_number': transaction.get('account_number') or False,
            'transaction_type': transaction.get('transaction_type') or False,
            'bank_feed_transaction_id': str(transaction['id']),
            'bank_feed_account_id': self.id,
            'bank_feed_pending': is_pending,
            'transaction_details': transaction.get('raw') or {
                key: value for key, value in (('reference', transaction.get('ref')),) if value
            },
        }
        foreign = currencies.get((transaction.get('foreign_currency_code') or '').upper())
        if foreign and foreign != currency and transaction.get('amount_currency'):
            values.update({
                'foreign_currency_id': foreign.id,
                'amount_currency': foreign.round(math.copysign(abs(transaction['amount_currency']),
                                                               transaction['amount'])),
            })
        return values

    def _get_foreign_currencies(self, transactions):
        codes = {(transaction.get('foreign_currency_code') or '').upper() for transaction in transactions
                 if transaction.get('amount_currency')} - {''}
        if not codes:
            return {}
        currencies = self.env['res.currency'].search([('name', 'in', list(codes))])
        return {currency.name: currency for currency in currencies}

    # -------------------------------------------------------------------------
    # Partners
    # -------------------------------------------------------------------------

    def _set_partners(self, lines_values):
        """ Set the partner of the new lines when it is certain: the one partner owning the bank account of
        the other party, else the one company with exactly its name """
        company = self.company_id
        cache = {}
        for values in lines_values:
            partner = self._find_partner(values.get('account_number'), values.get('partner_name'), company, cache)
            if partner:
                values['partner_id'] = partner.id

    def _find_partner(self, account_number, partner_name, company, cache):
        Partner = self.env['res.partner']
        sanitized = sanitize_account_number(account_number or '')
        if sanitized:
            key = ('account', sanitized)
            if key not in cache:
                PartnerBank = self.env['res.partner.bank']
                cache[key] = PartnerBank.search(
                    Domain('sanitized_account_number', '=', sanitized)
                    & Domain('partner_id.active', '=', True)
                    & Domain(PartnerBank._check_company_domain(company))
                ).partner_id.commercial_partner_id
            if len(cache[key]) == 1:
                return cache[key]
            if cache[key]:
                return Partner
        words = (partner_name or '').split()
        if not words:
            return Partner
        name = ' '.join(words).casefold()
        key = ('name', name)
        if key not in cache:
            pattern = '%' + '%'.join(escape_like_value(word) for word in words) + '%'
            companies = Partner.search(
                Domain('name', '=ilike', pattern) & Domain('is_company', '=', True)
                & Domain(Partner._check_company_domain(company))
            )
            cache[key] = companies.filtered(lambda partner: ' '.join((partner.name or '').split()).casefold() == name)
        return cache[key] if len(cache[key]) == 1 else Partner

    # -------------------------------------------------------------------------
    # Balance
    # -------------------------------------------------------------------------

    def _check_balance(self):
        """ Compare the balance of the bank with the balance of the transactions of the journal.

        :return: the warning when they differ
        """
        self.ensure_one()
        if not self.has_balance:
            self.write({'balance_mismatch': False, 'balance_difference': 0.0, 'journal_balance': 0.0})
            return ''
        journal = self.journal_id
        currency = journal.currency_id or journal.company_id.currency_id
        domain = [('journal_id', '=', journal.id), ('move_id.state', '=', 'posted')]
        if not self.connection_id.include_pending:
            domain.append(('bank_feed_pending', '=', False))
        [[journal_balance]] = self.env['account.bank.statement.line'].sudo()._read_group(domain, [], ['amount:sum'])
        difference = currency.round(self.balance - (journal_balance or 0.0))
        mismatch = not currency.is_zero(difference)
        self.write({
            'journal_balance': journal_balance or 0.0,
            'balance_difference': difference,
            'balance_mismatch': mismatch,
        })
        if not mismatch:
            return ''
        return self.env._(
            'The balance of the bank, %(bank)s, differs from the balance of the transactions of the journal '
            '%(journal)s, %(journal_balance)s, by %(difference)s. Check the transactions before the sync start '
            'date (an opening balance may be missing), the pending transactions, and the lines entered by hand.',
            bank=format_amount(self.env, self.balance, currency), journal=journal.display_name,
            journal_balance=format_amount(self.env, journal_balance or 0.0, currency),
            difference=format_amount(self.env, difference, currency),
        )
