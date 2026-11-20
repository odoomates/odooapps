from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


class OmReconcileItemsWizard(models.TransientModel):
    _name = 'om.reconcile.items.wizard'
    _description = 'Match Journal Items'
    _check_company_auto = True

    line_ids = fields.Many2many('account.move.line', string='Journal Items', required=True)
    company_id = fields.Many2one('res.company', compute='_compute_summary')
    company_currency_id = fields.Many2one('res.currency', compute='_compute_summary')
    account_id = fields.Many2one('account.account', string='Account', compute='_compute_summary')
    debit = fields.Monetary(currency_field='company_currency_id', compute='_compute_summary')
    credit = fields.Monetary(currency_field='company_currency_id', compute='_compute_summary')
    difference = fields.Monetary(currency_field='company_currency_id', compute='_compute_summary',
                                 help='Open amount left once the items are matched together.')
    is_balanced = fields.Boolean(compute='_compute_summary')

    # items of two accounts, or of several partners: moved to one of them first
    needs_transfer = fields.Boolean(compute='_compute_summary')
    line_account_ids = fields.Many2many('account.account', compute='_compute_summary')
    line_partner_ids = fields.Many2many('res.partner', compute='_compute_summary')
    transfer_account_id = fields.Many2one(
        'account.account', string='Transfer to Account', compute='_compute_transfer', store=True, readonly=False,
        domain="[('id', 'in', line_account_ids)]",
        help='The items on the other account are moved to this one by a journal entry before being matched.')
    transfer_partner_id = fields.Many2one(
        'res.partner', string='Transfer to Partner', compute='_compute_transfer', store=True, readonly=False,
        domain="[('id', 'in', line_partner_ids)]",
        help='The items of the other partners are moved to this one by the same journal entry.')

    allow_partials = fields.Boolean(
        string='Allow Partial Matching', default=True,
        help='When the items do not add up to zero, match them anyway and leave the difference open.')
    writeoff = fields.Boolean(string='Write Off the Difference')
    writeoff_model_id = fields.Many2one(
        'account.reconcile.model', string='Model', check_company=True,
        domain="[('rule_type', '!=', 'invoice_matching'), ('line_ids.account_id', '!=', False)]",
        help='Fill the write-off in from the first line of a reconciliation model.')
    writeoff_journal_id = fields.Many2one('account.journal', string='Journal', check_company=True,
                                          domain=[('type', '=', 'general')],
                                          compute='_compute_writeoff_journal_id', store=True, readonly=False)
    writeoff_account_id = fields.Many2one('account.account', string='Write-off Account', check_company=True,
                                          domain=[('account_type', '!=', 'off_balance')])
    writeoff_tax_ids = fields.Many2many(
        'account.tax', string='Taxes', check_company=True,
        domain=[('type_tax_use', 'in', ('sale', 'purchase', 'none'))],
        help='The difference includes these taxes: they are taken out of it and booked on their own accounts.')
    writeoff_date = fields.Date(string='Date', default=fields.Date.context_today)
    writeoff_label = fields.Char(string='Label', default=lambda self: _('Write-off'))
    lock_date_message = fields.Char(compute='_compute_lock_date_message')

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        if ('line_ids' in fields and not values.get('line_ids')
                and self.env.context.get('active_model') == 'account.move.line'):
            values['line_ids'] = [Command.set(self.env.context.get('active_ids') or [])]
        return values

    @api.depends('line_ids')
    def _compute_summary(self):
        for wizard in self:
            lines = wizard.line_ids
            summary = lines._om_matching_summary() if lines else {}
            currency = (self.env['res.currency'].browse(summary.get('company_currency_id'))
                        or self.env.company.currency_id)
            wizard.company_id = lines.company_id.root_id[:1] or self.env.company
            wizard.company_currency_id = currency
            wizard.account_id = summary.get('account_id') if len(lines.account_id) == 1 else False
            wizard.debit = summary.get('debit', 0.0)
            wizard.credit = summary.get('credit', 0.0)
            wizard.difference = summary.get('difference', 0.0)
            wizard.is_balanced = currency.is_zero(summary.get('difference', 0.0))
            wizard.line_account_ids = lines.account_id
            wizard.line_partner_ids = lines.partner_id.commercial_partner_id
            wizard.needs_transfer = len(lines.account_id) > 1 or len(lines.partner_id.commercial_partner_id) > 1

    @api.depends('line_ids')
    def _compute_transfer(self):
        for wizard in self:
            lines = wizard.line_ids
            # by default to the account and the partner of the larger side, e.g. the invoice rather than its payment
            biggest = lines.sorted(lambda line: abs(line.amount_residual), reverse=True)[:1]
            wizard.transfer_account_id = biggest.account_id if len(lines.account_id) > 1 else False
            wizard.transfer_partner_id = (biggest.partner_id.commercial_partner_id
                                          if len(lines.partner_id.commercial_partner_id) > 1 else False)

    @api.depends('company_id')
    def _compute_writeoff_journal_id(self):
        for wizard in self:
            wizard.writeoff_journal_id = self.env['account.journal'].search([
                *self.env['account.journal']._check_company_domain(wizard.company_id),
                ('type', '=', 'general'),
            ], limit=1)

    @api.depends('writeoff_date', 'writeoff_journal_id', 'writeoff_tax_ids', 'writeoff', 'needs_transfer')
    def _compute_lock_date_message(self):
        for wizard in self:
            wizard.lock_date_message = False
            if not wizard.writeoff_date or not (wizard.writeoff or wizard.needs_transfer):
                continue
            # Odoo 17: the lock dates of the company, without a journal
            violated = wizard.company_id._get_violated_lock_dates(wizard.writeoff_date, bool(wizard.writeoff_tax_ids))
            if violated:
                wizard.lock_date_message = _(
                    'The books are locked until %(date)s: the entry will be dated on the first open day after it.',
                    date=format_date(self.env, violated[-1][0]))

    @api.onchange('writeoff_model_id')
    def _onchange_writeoff_model_id(self):
        line = self.writeoff_model_id.line_ids.filtered('account_id')[:1]
        if line:
            self.writeoff_account_id = line.account_id
            self.writeoff_tax_ids = line.tax_ids
            self.writeoff_label = line.label or self.writeoff_model_id.name

    def _entry_date(self):
        """ The date of the entries created: the date chosen, or the first open day after the lock date. """
        self.ensure_one()
        date = self.writeoff_date or fields.Date.context_today(self)
        violated = self.company_id._get_violated_lock_dates(date, bool(self.writeoff_tax_ids))
        if violated:
            date = fields.Date.add(violated[-1][0], days=1)
        return date

    def action_reconcile(self):
        self.ensure_one()
        lines = self.line_ids
        if self.needs_transfer:
            if not self.writeoff_journal_id:
                raise UserError(_('Choose the journal of the transfer entry.'))
            partners = lines.partner_id.commercial_partner_id
            account = self.transfer_account_id or lines.account_id[:1]
            partner = (self.transfer_partner_id or partners[:1]) if len(partners) > 1 else partners[:1]
            lines = lines._om_transfer_to(account, partner, self.writeoff_journal_id, self._entry_date())
        writeoff = None
        if self.writeoff and not self.is_balanced:
            if not self.writeoff_account_id or not self.writeoff_journal_id:
                raise UserError(_('Choose the journal and the account of the write-off.'))
            writeoff = {
                'account_id': self.writeoff_account_id.id,
                'journal_id': self.writeoff_journal_id.id,
                'date': self._entry_date(),
                'label': self.writeoff_label,
                'tax_ids': self.writeoff_tax_ids.ids,
            }
        elif not self.is_balanced and not self.allow_partials:
            raise UserError(_('The items do not add up to zero: write the difference off, or allow partial matching.'))
        lines._om_reconcile_items(writeoff=writeoff)
        return {'type': 'ir.actions.act_window_close'}
