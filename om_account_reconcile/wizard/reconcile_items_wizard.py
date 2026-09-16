from odoo import api, fields, models, _
from odoo.exceptions import UserError


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

    writeoff = fields.Boolean(string='Write Off the Difference')
    writeoff_journal_id = fields.Many2one('account.journal', string='Journal', check_company=True,
                                          domain=[('type', '=', 'general')],
                                          compute='_compute_writeoff_journal_id', store=True, readonly=False)
    writeoff_account_id = fields.Many2one('account.account', string='Write-off Account', check_company=True,
                                          domain=[('account_type', '!=', 'off_balance')])
    writeoff_date = fields.Date(string='Date', default=fields.Date.context_today)
    writeoff_label = fields.Char(string='Label', default=lambda self: _('Write-off'))

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'line_ids' in fields_list and not values.get('line_ids') and self.env.context.get('active_model') == 'account.move.line':
            values['line_ids'] = [fields.Command.set(self.env.context.get('active_ids') or [])]
        return values

    @api.depends('line_ids')
    def _compute_summary(self):
        for wizard in self:
            lines = wizard.line_ids
            summary = lines._om_matching_summary() if lines else {}
            currency = self.env['res.currency'].browse(summary.get('company_currency_id')) or self.env.company.currency_id
            wizard.company_id = lines.company_id.root_id[:1] or self.env.company
            wizard.company_currency_id = currency
            wizard.account_id = summary.get('account_id') if len(lines.account_id) == 1 else False
            wizard.debit = summary.get('debit', 0.0)
            wizard.credit = summary.get('credit', 0.0)
            wizard.difference = summary.get('difference', 0.0)
            wizard.is_balanced = currency.is_zero(summary.get('difference', 0.0))

    @api.depends('company_id')
    def _compute_writeoff_journal_id(self):
        for wizard in self:
            wizard.writeoff_journal_id = self.env['account.journal'].search([
                *self.env['account.journal']._check_company_domain(wizard.company_id),
                ('type', '=', 'general'),
            ], limit=1)

    def action_reconcile(self):
        self.ensure_one()
        writeoff = None
        if self.writeoff and not self.is_balanced:
            if not self.writeoff_account_id or not self.writeoff_journal_id:
                raise UserError(_('Choose the journal and the account of the write-off.'))
            writeoff = {
                'account_id': self.writeoff_account_id.id,
                'journal_id': self.writeoff_journal_id.id,
                'date': self.writeoff_date,
                'label': self.writeoff_label,
            }
        self.line_ids._om_reconcile_items(writeoff=writeoff)
        return {'type': 'ir.actions.act_window_close'}
