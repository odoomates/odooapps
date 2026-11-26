from odoo import api, fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    bank_feed_account_ids = fields.One2many('bank.feed.account', 'journal_id', string='Bank Feed Accounts')
    bank_feed_account_id = fields.Many2one(
        'bank.feed.account', string='Bank Feed Account', compute='_compute_bank_feed')
    bank_feed_connection_id = fields.Many2one(
        'bank.feed.connection', string='Bank Feed Connection', compute='_compute_bank_feed')
    bank_feed_state = fields.Selection(
        selection=lambda self: self.env['bank.feed.connection']._fields['state'].selection,
        string='Bank Feed Status', compute='_compute_bank_feed')
    bank_feed_last_sync = fields.Datetime(string='Bank Feed Last Sync', compute='_compute_bank_feed')
    bank_feed_consent_expiry_date = fields.Date(string='Bank Feed Consent Expiry', compute='_compute_bank_feed')
    bank_feed_balance_mismatch = fields.Boolean(string='Bank Feed Balance Mismatch', compute='_compute_bank_feed')

    def _get_bank_statements_available_sources(self):
        return super()._get_bank_statements_available_sources() + [('bank_feed', self.env._('Bank Feed'))]

    @api.depends('bank_feed_account_ids.last_sync', 'bank_feed_account_ids.balance_mismatch',
                 'bank_feed_account_ids.connection_id.state')
    def _compute_bank_feed(self):
        for journal in self:
            account = journal.sudo().bank_feed_account_ids[:1]
            connection = account.connection_id
            journal.bank_feed_account_id = account
            journal.bank_feed_connection_id = connection
            journal.bank_feed_state = connection.state or False
            journal.bank_feed_last_sync = account.last_sync or connection.last_sync
            journal.bank_feed_consent_expiry_date = connection.consent_expiry_date
            journal.bank_feed_balance_mismatch = account.balance_mismatch

    def action_bank_feed_connect(self):
        """ Connect the bank of this journal through a bank feed provider """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Connect a Bank Feed'),
            'res_model': 'bank.feed.connect.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_journal_id': self.id},
        }

    def action_bank_feed_sync(self):
        self.ensure_one()
        return self.bank_feed_connection_id.action_sync()

    def action_bank_feed_open(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'bank.feed.connection',
            'res_id': self.bank_feed_connection_id.id,
            'view_mode': 'form',
        }

    def action_bank_feed_renew(self):
        self.ensure_one()
        return self.bank_feed_connection_id.action_renew()

    def action_bank_feed_disconnect(self):
        """ Stop the bank feed of this journal; the connection is removed at the provider when it feeds no
        other journal """
        self.ensure_one()
        account = self.bank_feed_account_id
        connection = account.connection_id
        connection._check_manager()
        if not connection:
            return False
        if connection.account_ids.journal_id == self:
            connection.action_disconnect()
        else:
            account.sudo().journal_id = False
            connection.message_post(body=self.env._(
                'The journal %(journal)s no longer receives the transactions of %(account)s.',
                journal=self.display_name, account=account.display_name))
        return True
