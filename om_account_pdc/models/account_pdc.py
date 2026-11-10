from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class AccountPdc(models.Model):
    """ A post-dated cheque, received from a customer or issued to a vendor. Registering it moves the amount
    from the partner to the PDC account and settles the invoices; clearing it on its date moves it to the
    bank; a bounce takes it back and opens the invoices again. """
    _name = 'account.pdc'
    _description = 'Post-dated Cheque'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'cheque_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='/')
    pdc_type = fields.Selection(
        [('receive', 'Received'), ('issue', 'Issued')], string='Type', required=True, default='receive',
        tracking=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    partner_id = fields.Many2one('res.partner', string='Partner', required=True, tracking=True, check_company=True)
    amount = fields.Monetary(required=True, tracking=True)
    cheque_number = fields.Char(string='Cheque Number', tracking=True)
    bank_name = fields.Char(string='Drawn On', help="The bank the cheque is drawn on.")
    date = fields.Date(string='Received On', required=True, default=fields.Date.context_today,
                       help="The day the cheque is received or issued: the date of its registration.")
    cheque_date = fields.Date(string='Cheque Date', required=True, tracking=True,
                              help="The date written on the cheque: it cannot be cashed before it.")
    days_to_maturity = fields.Integer(compute='_compute_days_to_maturity')
    journal_id = fields.Many2one(
        'account.journal', string='Bank', required=True, check_company=True, domain="[('type', '=', 'bank')]",
        help="The bank account the cheque is cleared into, or paid from.")
    pdc_account_id = fields.Many2one(
        'account.account', string='PDC Account', required=True, check_company=True,
        compute='_compute_pdc_account_id', store=True, readonly=False, precompute=True,
        help="The account holding the cheques until they are cleared: an asset for the cheques received, a "
             "liability for the cheques issued.")
    invoice_ids = fields.Many2many(
        'account.move', string='Invoices', check_company=True,
        domain="[('partner_id.commercial_partner_id', '=', commercial_partner_id), ('state', '=', 'posted'), "
               "('payment_state', 'in', ('not_paid', 'partial')), "
               "('move_type', 'in', ('out_invoice', 'in_refund', 'in_invoice', 'out_refund'))]",
        help="The invoices or bills the cheque pays: they are matched when it is registered.")
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id')
    memo = fields.Char()
    state = fields.Selection(
        [('draft', 'Draft'), ('registered', 'Registered'), ('deposited', 'Deposited'), ('cleared', 'Cleared'),
         ('bounced', 'Bounced'), ('cancel', 'Cancelled')],
        default='draft', required=True, tracking=True, readonly=True, copy=False)
    register_move_id = fields.Many2one('account.move', string='Registration Entry', readonly=True, copy=False)
    clear_move_id = fields.Many2one('account.move', string='Clearing Entry', readonly=True, copy=False)
    bounce_move_id = fields.Many2one('account.move', string='Bounce Entry', readonly=True, copy=False)
    clear_date = fields.Date(string='Cleared On', readonly=True, copy=False)
    move_count = fields.Integer(compute='_compute_move_count')

    _positive_amount = models.Constraint('CHECK(amount > 0)', 'The amount of a cheque must be positive.')

    @api.constrains('invoice_ids', 'pdc_type')
    def _check_invoices(self):
        for pdc in self:
            kinds = ('out_invoice', 'in_refund') if pdc.pdc_type == 'receive' else ('in_invoice', 'out_refund')
            if any(invoice.move_type not in kinds for invoice in pdc.invoice_ids):
                raise UserError(_("A cheque received pays customer invoices, a cheque issued vendor bills."))

    @api.depends('cheque_date')
    def _compute_days_to_maturity(self):
        today = fields.Date.context_today(self)
        for pdc in self:
            pdc.days_to_maturity = (pdc.cheque_date - today).days if pdc.cheque_date else 0

    @api.depends('pdc_type', 'company_id')
    def _compute_pdc_account_id(self):
        for pdc in self:
            pdc.pdc_account_id = pdc.company_id.pdc_receivable_account_id if pdc.pdc_type == 'receive' \
                else pdc.company_id.pdc_payable_account_id

    @api.depends('register_move_id', 'clear_move_id', 'bounce_move_id')
    def _compute_move_count(self):
        for pdc in self:
            pdc.move_count = len(pdc.register_move_id | pdc.clear_move_id | pdc.bounce_move_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                code = 'account.pdc.receive' if vals.get('pdc_type', self.env.context.get('default_pdc_type')) != 'issue' \
                    else 'account.pdc.issue'
                vals['name'] = self.env['ir.sequence'].next_by_code(code) or '/'
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(pdc.state not in ('draft', 'cancel') for pdc in self):
            raise UserError(_("Only a draft or cancelled cheque can be deleted."))

    # ------------------------------------------------------------------
    # Accounting
    # ------------------------------------------------------------------
    def _partner_account(self):
        partner = self.partner_id.with_company(self.company_id)
        return partner.property_account_receivable_id if self.pdc_type == 'receive' \
            else partner.property_account_payable_id

    def _journal(self):
        journal = self.company_id.pdc_journal_id
        if not journal:
            raise UserError(_("Set the PDC journal in the accounting settings first."))
        return journal

    def _move(self, date, debit_account, credit_account, label, journal=None, partner_debit=False,
              partner_credit=False):
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': (journal or self._journal()).id,
            'company_id': self.company_id.id,
            'date': date,
            'ref': label,
            'partner_id': partner.id,
            'line_ids': [
                Command.create({'name': label, 'account_id': debit_account.id, 'debit': self.amount,
                                'partner_id': partner.id}),
                Command.create({'name': label, 'account_id': credit_account.id, 'credit': self.amount,
                                'partner_id': partner.id}),
            ],
        })
        move.action_post()
        return move

    def _label(self, action):
        return '%s %s%s' % (action, self.name, (' - %s' % self.cheque_number) if self.cheque_number else '')

    def action_register(self):
        """ Out of the partner, into the PDC account, and the invoices settled. """
        for pdc in self.filtered(lambda pdc: pdc.state == 'draft'):
            if not pdc.pdc_account_id:
                raise UserError(_("Set the PDC accounts in the accounting settings, or a PDC account on the cheque."))
            partner_account = pdc._partner_account()
            if pdc.pdc_type == 'receive':
                move = pdc._move(pdc.date, pdc.pdc_account_id, partner_account, pdc._label(_("PDC received")))
            else:
                move = pdc._move(pdc.date, partner_account, pdc.pdc_account_id, pdc._label(_("PDC issued")))
            pdc.write({'register_move_id': move.id, 'state': 'registered'})
            pdc._reconcile_invoices()
        return True

    def _reconcile_invoices(self):
        self.ensure_one()
        if not self.invoice_ids:
            return
        account = self._partner_account()
        lines = (self.register_move_id.line_ids | self.invoice_ids.line_ids).filtered(
            lambda line: line.account_id == account and not line.reconciled)
        lines.reconcile()

    def action_deposit(self):
        self.filtered(lambda pdc: pdc.state == 'registered' and pdc.pdc_type == 'receive').state = 'deposited'
        return True

    def action_clear(self):
        """ On or after the cheque date: from the PDC account to the bank. """
        today = fields.Date.context_today(self)
        for pdc in self:
            if pdc.state not in ('registered', 'deposited'):
                raise UserError(_("Only a registered or deposited cheque can be cleared."))
            if pdc.cheque_date > today:
                raise UserError(_("The cheque %(cheque)s cannot be cleared before its date, %(date)s.",
                                  cheque=pdc.name, date=pdc.cheque_date))
            bank = pdc.journal_id.default_account_id
            if not bank:
                raise UserError(_("The journal %(journal)s has no bank account.", journal=pdc.journal_id.display_name))
            date = max(pdc.cheque_date, pdc.date)
            if pdc.pdc_type == 'receive':
                move = pdc._move(date, bank, pdc.pdc_account_id, pdc._label(_("PDC cleared")), journal=pdc.journal_id)
            else:
                move = pdc._move(date, pdc.pdc_account_id, bank, pdc._label(_("PDC cleared")), journal=pdc.journal_id)
            pdc.write({'clear_move_id': move.id, 'clear_date': date, 'state': 'cleared'})
        return True

    def action_bounce(self):
        """ The cheque is refused: the registration is undone and the invoices are open again. """
        for pdc in self:
            if pdc.state not in ('registered', 'deposited'):
                raise UserError(_("Only a registered or deposited cheque can bounce."))
            register = pdc.register_move_id
            register.line_ids.filtered(lambda line: line.account_id == pdc._partner_account()).remove_move_reconcile()
            reversal = register._reverse_moves([{
                'date': max(fields.Date.context_today(pdc), pdc.date),
                'ref': pdc._label(_("PDC bounced")),
            }], cancel=True)
            pdc.write({'bounce_move_id': reversal.id, 'state': 'bounced'})
            pdc.message_post(body=_("The cheque bounced: its invoices are open again."))
        return True

    def action_cancel(self):
        for pdc in self:
            if pdc.state != 'draft':
                raise UserError(_("Only a draft cheque can be cancelled; a registered one bounces."))
        self.state = 'cancel'
        return True

    def action_draft(self):
        self.filtered(lambda pdc: pdc.state == 'cancel').state = 'draft'
        return True

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Journal Entries"),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', (self.register_move_id | self.clear_move_id | self.bounce_move_id).ids)],
            'context': {'create': False},
        }

    @api.model
    def _cron_remind_maturity(self):
        """ An activity on the cheques reaching their date, for whoever has to cash or pay them. """
        today = fields.Date.context_today(self)
        due = self.search([('state', 'in', ('registered', 'deposited')), ('cheque_date', '<=', today)])
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for pdc in due:
            if activity_type and not pdc.activity_ids.filtered(lambda act: act.activity_type_id == activity_type):
                pdc.activity_schedule(
                    'mail.mail_activity_data_todo', date_deadline=pdc.cheque_date,
                    summary=_("Clear the cheque %(cheque)s", cheque=pdc.name),
                    user_id=(pdc.create_uid or self.env.user).id)
