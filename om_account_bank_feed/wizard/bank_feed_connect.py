from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.bank_feed_account import _default_sync_start_date


class BankFeedConnectWizard(models.TransientModel):
    _name = 'bank.feed.connect.wizard'
    _description = 'Connect a Bank Feed'

    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, domain="[('type', 'in', ('bank', 'credit'))]")
    company_id = fields.Many2one(related='journal_id.company_id')
    mode = fields.Selection([
        ('new', 'Connect a new bank'),
        ('existing', 'Use an account of a connected bank'),
    ], string='Connection', required=True, default='new')
    provider = fields.Selection(selection='_get_provider_selection', string='Provider')
    name = fields.Char(string='Name', compute='_compute_name', store=True, readonly=False)
    sync_start_date = fields.Date(
        string='Sync From', required=True, default=_default_sync_start_date,
        help="The first sync imports the transactions from this date.")
    feed_account_id = fields.Many2one(
        'bank.feed.account', string='Bank Account',
        domain="[('company_id', '=', company_id), ('journal_id', '=', False), "
               "('connection_id.state', 'in', ('connected', 'expiring'))]")
    has_providers = fields.Boolean(compute='_compute_has_providers')

    @api.model
    def _get_provider_selection(self):
        return self.env['bank.feed.connection']._fields['provider'].selection

    def _compute_has_providers(self):
        for wizard in self:
            wizard.has_providers = bool(self._get_provider_selection())

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        selection = self._get_provider_selection()
        if 'provider' in fields and len(selection) == 1:
            values['provider'] = selection[0][0]
        return values

    @api.depends('journal_id')
    def _compute_name(self):
        for wizard in self:
            wizard.name = wizard.journal_id.name

    def action_connect(self):
        self.ensure_one()
        journal = self.journal_id
        if journal.bank_feed_account_ids:
            raise UserError(self.env._('The journal %s already has a bank feed.', journal.display_name))
        if self.mode == 'existing':
            if not self.feed_account_id:
                raise UserError(self.env._('Choose the bank account of the journal.'))
            self.feed_account_id.write({'journal_id': journal.id, 'sync_start_date': self.sync_start_date})
            journal.bank_statements_source = 'bank_feed'
            return journal.action_bank_feed_open()
        if not self.provider:
            raise UserError(self.env._('Install a bank feed provider module first, then choose it here.'))
        connection = self.env['bank.feed.connection'].create({
            'name': self.name or journal.name,
            'provider': self.provider,
            'company_id': journal.company_id.id,
            'pending_journal_id': journal.id,
            'sync_start_date': self.sync_start_date,
        })
        journal.bank_statements_source = 'bank_feed'
        return connection.action_connect()
