import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import consteq, format_date

_logger = logging.getLogger(__name__)

TOKEN_VALIDITY = timedelta(hours=2)


class BankFeedError(UserError):
    """ An error of a bank feed provider. ``expired`` tells that the consent of the bank is no longer valid,
    so that the connection must be renewed instead of tried again. """

    def __init__(self, message, expired=False):
        super().__init__(message)
        self.expired = expired


class BankFeedConnection(models.Model):
    _name = 'bank.feed.connection'
    _description = 'Bank Feed Connection'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, index=True, default=lambda self: self.env.company)
    provider = fields.Selection(
        selection=[], string='Provider', required=True, tracking=True,
        help="The bank feed provider connecting to the bank. Each provider is added by its own module.")
    state = fields.Selection([
        ('draft', 'Not Connected'),
        ('connected', 'Connected'),
        ('expiring', 'Expiring Soon'),
        ('expired', 'Expired'),
        ('error', 'Error'),
    ], string='Status', default='draft', required=True, copy=False, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Responsible', default=lambda self: self.env.user,
        domain="[('share', '=', False)]",
        help="Receives the reminders before the consent of the bank expires, and the errors of the sync.")
    institution_name = fields.Char(string='Bank', copy=False)
    provider_reference = fields.Char(
        string='Provider Connection ID', copy=False, readonly=True,
        help="The identifier of this connection at the provider.")
    consent_expiry_date = fields.Date(
        string='Consent Expires On', copy=False, tracking=True,
        help="After this date the bank refuses to share the transactions until the consent is renewed.")
    reminder_date = fields.Date(
        string='Reminder Sent For', copy=False, readonly=True,
        help="The consent expiry date the last reminder was sent for.")
    last_sync = fields.Datetime(string='Last Sync', copy=False, readonly=True)
    error_message = fields.Text(string='Error', copy=False, readonly=True)
    include_pending = fields.Boolean(
        string='Import Pending Transactions',
        help="Also import the transactions the bank has not booked yet. They are marked as pending, replaced by "
             "the booked transaction when it comes, and removed when the bank drops them. Left unticked, only "
             "booked transactions are imported.")
    account_ids = fields.One2many('bank.feed.account', 'connection_id', string='Bank Accounts')
    account_count = fields.Integer(compute='_compute_account_count', string='Accounts')
    journal_ids = fields.Many2many('account.journal', compute='_compute_journal_ids', string='Journals')
    log_ids = fields.One2many('bank.feed.log', 'connection_id', string='Sync Logs')
    log_count = fields.Integer(compute='_compute_log_count', string='Logs')
    pending_journal_id = fields.Many2one(
        'account.journal', string='Journal to Map', copy=False, check_company=True,
        help="The journal the connection was started from: it is mapped to the bank account when the bank "
             "returns a single account in the currency of the journal.")
    sync_start_date = fields.Date(
        string='Sync From', default=lambda self: fields.Date.context_today(self).replace(day=1),
        help="The first sync of the new bank accounts imports the transactions from this date.")
    access_token = fields.Char(copy=False, groups='base.group_system')
    access_token_expiry = fields.Datetime(copy=False, groups='base.group_system')

    @api.depends('account_ids')
    def _compute_account_count(self):
        for connection in self:
            connection.account_count = len(connection.account_ids)

    @api.depends('account_ids.journal_id')
    def _compute_journal_ids(self):
        for connection in self:
            connection.journal_ids = connection.account_ids.journal_id

    def _compute_log_count(self):
        counts = dict(self.env['bank.feed.log']._read_group(
            [('connection_id', 'in', self.ids)], ['connection_id'], ['__count']))
        for connection in self:
            connection.log_count = counts.get(connection, 0)

    # -------------------------------------------------------------------------
    # Provider hooks: a provider module overrides them for its own value of ``provider``
    # -------------------------------------------------------------------------

    def _provider_not_supported(self):
        raise UserError(self.env._('The provider of the connection %s is not installed.', self.display_name))

    def _provider_start_consent(self, return_url):
        """ Start the consent of the bank at the provider.

        :param str return_url: where the provider sends the user back once the consent is given
        :return: the URL of the consent page of the provider
        """
        self._provider_not_supported()

    def _provider_renew_consent(self, return_url):
        """ Renew the consent of an existing connection.

        :return: the URL of the renewal page of the provider
        """
        self._provider_not_supported()

    def _provider_handle_callback(self, params):
        """ Read the parameters the provider sends back to the callback URL: store the reference of the
        connection, the bank and the consent expiry date. Raise a ``BankFeedError`` when the consent failed. """
        self._provider_not_supported()

    def _provider_refresh(self):
        """ Ask the provider to fetch fresh data from the bank, when it supports it. The data comes in a
        later sync when the provider fetches it in the background. """
        return

    def _provider_fetch_accounts(self):
        """ :return: the bank accounts of the connection, a list of dicts with the keys

            - ``ref``: the identifier of the account at the provider (required)
            - ``name``, ``account_number`` (IBAN or number), ``currency_code``
            - ``balance`` and ``balance_date`` (datetime): the balance given by the bank, when known
        """
        self._provider_not_supported()

    def _provider_fetch_transactions(self, feed_account, date_from):
        """ :param feed_account: the ``bank.feed.account`` to read
        :param date date_from: the first date to read
        :return: the transactions of the account, a list of dicts with the keys

            - ``id``: the identifier of the transaction at the provider, unique for the account (required)
            - ``date`` (date), ``amount`` (signed, in the currency of the account) (required)
            - ``currency_code``, ``payment_ref``, ``ref``, ``partner_name``, ``account_number``,
              ``transaction_type``
            - ``foreign_currency_code`` and ``amount_currency``: the original amount of the transaction
            - ``pending``: True when the bank has not booked it yet
            - ``raw``: the transaction as the provider returned it, kept on the statement line
        """
        self._provider_not_supported()

    def _provider_disconnect(self):
        """ Remove the connection at the provider, revoking the consent. """
        return

    # -------------------------------------------------------------------------
    # Consent and callback
    # -------------------------------------------------------------------------

    def _check_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(self.env._('Only the accounting administrators manage the bank feeds.'))

    def _prepare_return_url(self):
        """ :return: the callback URL of this connection, with a new single use token """
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        self.sudo().write({
            'access_token': token,
            'access_token_expiry': fields.Datetime.now() + TOKEN_VALIDITY,
        })
        return f'{self.get_base_url()}/bank_feed/callback/{self.id}/{token}'

    def _check_access_token(self, token):
        """ :return: whether the token is the current token of the connection and still valid """
        self.ensure_one()
        connection = self.sudo()
        return bool(
            token and connection.access_token and consteq(connection.access_token, token)
            and connection.access_token_expiry and connection.access_token_expiry >= fields.Datetime.now()
        )

    def action_connect(self):
        """ Open the consent page of the provider """
        self.ensure_one()
        self._check_manager()
        url = self._provider_start_consent(self._prepare_return_url())
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'self'}

    def action_renew(self):
        """ Open the renewal page of the provider, for a consent that expires or has expired """
        self.ensure_one()
        self._check_manager()
        if not self.provider_reference:
            return self.action_connect()
        url = self._provider_renew_consent(self._prepare_return_url())
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'self'}

    def _handle_callback(self, params):
        """ The user is back from the consent page of the provider: read the accounts of the bank and map the
        journal the connection was started from. """
        self.ensure_one()
        self.sudo().write({'access_token': False, 'access_token_expiry': False})
        renewal = bool(self.provider_reference)
        try:
            self._provider_handle_callback(params)
            self._update_accounts()
        except BankFeedError as error:
            self.write({'state': 'expired' if error.expired else 'error', 'error_message': str(error)})
            self._log('error', str(error))
            return False
        self.write({'state': 'connected', 'error_message': False, 'reminder_date': False})
        self._close_reminders()
        self._map_pending_journal()
        if renewal:
            body = self.env._('The consent of the bank was renewed until %s.',
                              format_date(self.env, self.consent_expiry_date) if self.consent_expiry_date else '-')
        else:
            body = self.env._('Connected to %(bank)s: %(count)s bank account(s) found.',
                              bank=self.institution_name or self.name, count=len(self.account_ids))
        self.message_post(body=body)
        return True

    def _map_pending_journal(self):
        """ Map the journal the connection was started from to the one account of the bank in its currency """
        journal = self.pending_journal_id
        if not journal:
            return
        self.pending_journal_id = False
        if journal.bank_feed_account_ids:
            return
        currency = journal.currency_id or journal.company_id.currency_id
        candidates = self.account_ids.filtered(
            lambda account: not account.journal_id and (not account.currency_id or account.currency_id == currency))
        if len(candidates) == 1:
            candidates.journal_id = journal

    def _update_accounts(self):
        """ Create or update the bank accounts of the connection from the provider """
        self.ensure_one()
        Currency = self.env['res.currency'].with_context(active_test=False)
        by_ref = {account.provider_account_ref: account for account in self.account_ids}
        for values in self._provider_fetch_accounts():
            ref = str(values['ref'])
            currency = values.get('currency_code') and Currency.search(
                [('name', '=', values['currency_code'].upper())], limit=1)
            vals = {
                'name': values.get('name') or ref,
                'account_number': values.get('account_number') or False,
                'currency_code': (values.get('currency_code') or '').upper() or False,
                'currency_id': currency.id if currency else False,
                'balance': values.get('balance') or 0.0,
                'balance_date': values.get('balance_date') or False,
                'has_balance': values.get('balance') is not None,
            }
            account = by_ref.get(ref)
            if account:
                account.write(vals)
            else:
                by_ref[ref] = self.env['bank.feed.account'].create({
                    **vals, 'connection_id': self.id, 'provider_account_ref': ref,
                    **({'sync_start_date': self.sync_start_date} if self.sync_start_date else {}),
                })

    # -------------------------------------------------------------------------
    # Sync
    # -------------------------------------------------------------------------

    def action_sync(self):
        """ Sync Now: fetch the new transactions of all the mapped accounts """
        if not self.env.user.has_group('account.group_account_basic'):
            raise AccessError(self.env._('You are not allowed to sync the bank feeds.'))
        connections = self.sudo()
        imported = 0
        errors = []
        for connection in connections:
            if connection.state == 'draft':
                raise UserError(self.env._('The connection %s is not connected yet.', connection.display_name))
            if not connection.account_ids.journal_id:
                raise UserError(self.env._(
                    'Map the bank accounts of %s to their journals before the sync.', connection.display_name))
            imported += connection._sync()
            if connection.state in ('error', 'expired') and connection.error_message:
                errors.append(f'{connection.display_name}: {connection.error_message}')
        if errors:
            message = '\n'.join(errors)
            notification_type = 'danger'
        else:
            message = self.env._('%s new transaction(s) imported.', imported)
            notification_type = 'success'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': notification_type,
                'message': message,
                'sticky': bool(errors),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _sync(self):
        """ Fetch the new transactions of the mapped accounts of the connection.

        :return: the number of statement lines created
        """
        self.ensure_one()
        imported = 0
        try:
            with self.env.cr.savepoint():
                self._provider_refresh()
                self._update_accounts()
                for account in self.account_ids.filtered('journal_id'):
                    imported += account._sync_transactions()
        except BankFeedError as error:
            values = {'state': 'expired' if error.expired else 'error', 'error_message': str(error)}
            self.env.invalidate_all()
            self.write(values)
            self._log('error', str(error))
            if error.expired:
                self._send_reminder(expired=True)
            return 0
        values = {'last_sync': fields.Datetime.now(), 'error_message': False}
        if self.state == 'error':
            values['state'] = 'connected'
        self.write(values)
        self._update_consent_state()
        return imported

    @api.model
    def _cron_sync(self):
        """ Sync the connections whose consent is valid, one by one """
        connections = self.search([
            ('state', 'in', ('connected', 'expiring', 'error')),
            ('account_ids.journal_id', '!=', False),
        ])
        self.env['ir.cron']._commit_progress(remaining=len(connections))
        for connection in connections:
            try:
                connection._sync()
            except Exception as error:  # one failing provider must not stop the others
                _logger.exception("Bank feed sync of connection %s failed", connection.id)
                self.env.invalidate_all()
                connection.write({'state': 'error', 'error_message': str(error)})
                connection._log('error', str(error))
            if not self.env['ir.cron']._commit_progress(1):
                break

    # -------------------------------------------------------------------------
    # Consent expiry
    # -------------------------------------------------------------------------

    def _update_consent_state(self):
        """ Set the state from the consent expiry date and send the reminder before it expires """
        today = fields.Date.context_today(self)
        for connection in self.filtered(lambda conn: conn.state in ('connected', 'expiring')
                                        and conn.consent_expiry_date):
            expiry = connection.consent_expiry_date
            if expiry < today:
                connection.state = 'expired'
                connection._send_reminder(expired=True)
            elif expiry <= today + timedelta(days=connection.company_id.bank_feed_reminder_days):
                connection.state = 'expiring'
                connection._send_reminder()
            elif connection.state == 'expiring':
                connection.state = 'connected'

    def _send_reminder(self, expired=False):
        """ Schedule an activity for the responsible, once per expiry date and state """
        self.ensure_one()
        today = fields.Date.context_today(self)
        expiry = self.consent_expiry_date or today
        if expired:
            expiry = min(expiry, today)
        key = expiry + timedelta(days=1) if expired else expiry
        if self.reminder_date == key:
            return
        self.reminder_date = key
        bank = self.institution_name or self.name
        if expired:
            summary = self.env._('Bank feed consent expired')
            note = self.env._('The consent of %(bank)s expired on %(date)s: the transactions are no longer '
                              'fetched. Open the connection and click Renew Consent.',
                              bank=bank, date=format_date(self.env, expiry))
            deadline = today
        else:
            summary = self.env._('Renew the bank feed consent')
            note = self.env._('The consent of %(bank)s expires on %(date)s. Open the connection and click '
                              'Renew Consent to keep the transactions coming.',
                              bank=bank, date=format_date(self.env, expiry))
            deadline = min(expiry, today + timedelta(days=1))
        user = self.user_id or self.env.ref('base.user_admin', raise_if_not_found=False) or self.env.user
        self.activity_schedule('mail.mail_activity_data_todo', date_deadline=deadline, summary=summary, note=note,
                               user_id=user.id)

    def _close_reminders(self):
        activities = self.activity_ids.filtered(
            lambda activity: activity.activity_type_id == self.env.ref('mail.mail_activity_data_todo'))
        if activities:
            activities.action_feedback(feedback=self.env._('Consent renewed.'))

    @api.model
    def _cron_check_consents(self):
        self.search([('state', 'in', ('connected', 'expiring')), ('consent_expiry_date', '!=', False)]) \
            ._update_consent_state()

    # -------------------------------------------------------------------------
    # Disconnect, logs
    # -------------------------------------------------------------------------

    def action_disconnect(self):
        """ Remove the connection at the provider and stop the sync of its journals. The statement lines
        already imported stay. """
        self._check_manager()
        for connection in self:
            if connection.provider_reference:
                connection._provider_disconnect()
            connection.account_ids.unlink()
            connection.write({
                'state': 'draft',
                'provider_reference': False,
                'consent_expiry_date': False,
                'reminder_date': False,
                'error_message': False,
            })
            connection.sudo().write({'access_token': False, 'access_token_expiry': False})
            connection.activity_unlink(['mail.mail_activity_data_todo'])
            connection.message_post(body=self.env._('Disconnected from the bank.'))
        return True

    def _log(self, level, message, account=None, **counts):
        return self.env['bank.feed.log'].sudo().create([{
            'connection_id': connection.id,
            'account_id': account.id if account else False,
            'level': level,
            'message': message,
            **counts,
        } for connection in self])

    def action_view_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_account_bank_feed.action_bank_feed_log')
        action['domain'] = [('connection_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    @api.ondelete(at_uninstall=False)
    def _unlink_disconnect(self):
        for connection in self.filtered('provider_reference'):
            try:
                connection._provider_disconnect()
            except UserError as error:
                _logger.warning("The connection %s could not be removed at the provider: %s", connection.id, error)
