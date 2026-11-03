import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# what a payment of a sent batch keeps: the bank already has it in the file
LOCKED_PAYMENT_FIELDS = {
    'amount', 'currency_id', 'partner_id', 'partner_bank_id', 'journal_id', 'payment_method_line_id',
    'payment_type', 'date', 'memo', 'batch_payment_id',
}


class AccountBatchPayment(models.Model):
    _name = 'account.batch.payment'
    _description = 'Batch Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='/')
    batch_type = fields.Selection(
        [('outbound', 'Send Money'), ('inbound', 'Receive Money')],
        string='Type', required=True, default='outbound', tracking=True)
    journal_id = fields.Many2one(
        'account.journal', string='Bank', required=True, check_company=True, tracking=True,
        domain="[('type', '=', 'bank')]")
    company_id = fields.Many2one(related='journal_id.company_id', store=True, index=True)
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True)
    payment_method_line_id = fields.Many2one(
        'account.payment.method.line', string='Payment Method', required=True, tracking=True,
        compute='_compute_payment_method_line_id', store=True, readonly=False, precompute=True,
        domain="[('journal_id', '=', journal_id), ('payment_type', '=', batch_type)]")
    payment_method_code = fields.Char(related='payment_method_line_id.code')
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('sent', 'Sent'), ('reconciled', 'Reconciled')],
        required=True, default='draft', copy=False, tracking=True, index=True,
        compute='_compute_state', store=True, readonly=False,
        help="Draft: the payments can still change.\n"
             "Sent: the file went to the bank or the deposit was made; the payments are locked.\n"
             "Reconciled: every payment of the batch is matched with a transaction of the bank.")
    payment_ids = fields.One2many('account.payment', 'batch_payment_id', string='Payments')
    payment_count = fields.Integer(compute='_compute_payment_count')
    amount = fields.Monetary(compute='_compute_amount', store=True, currency_field='currency_id')
    layout_id = fields.Many2one(
        'account.batch.payment.layout', string='Bank File Layout', check_company=True,
        compute='_compute_layout_id', store=True, readonly=False,
        help="The layout of the file uploaded to the bank. Leave empty when the bank needs no file, "
             "e.g. for a deposit of cheques.")
    export_file = fields.Binary(string='Bank File', attachment=True, copy=False, readonly=True)
    export_filename = fields.Char(string='File Name', copy=False, readonly=True)
    export_date = fields.Datetime(string='Generated On', copy=False, readonly=True)
    statement_line_ids = fields.Many2many(
        'account.bank.statement.line', compute='_compute_statement_line_ids', string='Bank Transactions')

    @api.depends('journal_id')
    def _compute_currency_id(self):
        for batch in self:
            batch.currency_id = batch.journal_id.currency_id or batch.journal_id.company_id.currency_id

    @api.depends('journal_id', 'batch_type')
    def _compute_payment_method_line_id(self):
        for batch in self:
            lines = batch.journal_id._get_available_payment_method_lines(batch.batch_type)
            if batch.payment_method_line_id not in lines:
                batch.payment_method_line_id = lines[:1]

    @api.depends('journal_id', 'batch_type')
    def _compute_layout_id(self):
        for batch in self:
            if batch.batch_type == 'outbound':
                batch.layout_id = batch.journal_id.om_batch_layout_id
            elif batch.journal_id.om_batch_layout_id != batch.layout_id:
                batch.layout_id = False

    @api.depends('payment_ids.state')
    def _compute_payment_count(self):
        for batch in self:
            batch.payment_count = len(batch._om_active_payments())

    @api.depends('payment_ids.amount', 'payment_ids.state', 'payment_ids.currency_id')
    def _compute_amount(self):
        for batch in self:
            batch.amount = sum(batch._om_active_payments().mapped('amount'))

    @api.depends('payment_ids.is_matched', 'payment_ids.state', 'payment_ids.move_id')
    def _compute_state(self):
        for batch in self:
            if batch.state not in ('sent', 'reconciled'):
                batch.state = batch.state or 'draft'
                continue
            payments = batch._om_active_payments()
            batch.state = 'reconciled' if payments and all(payments.mapped('om_is_cleared')) else 'sent'

    def _compute_statement_line_ids(self):
        for batch in self:
            batch.statement_line_ids = self.env['account.bank.statement.line'].search([
                ('om_batch_payment_ids', 'in', batch.payment_ids.ids),
            ]) if batch.payment_ids else False

    @api.model_create_multi
    def create(self, vals_list):
        batches = super().create(vals_list)
        for batch in batches.filtered(lambda batch: batch.name == '/'):
            code = 'account.batch.payment.%s' % ('in' if batch.batch_type == 'inbound' else 'out')
            batch.name = self.env['ir.sequence'].with_company(batch.company_id).next_by_code(
                code, sequence_date=batch.date) or '/'
        return batches

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(batch.state != 'draft' for batch in self):
            raise UserError(_('Only a draft batch can be deleted; set it back to draft first.'))

    def _om_active_payments(self):
        """ The payments the batch pays or receives: the cancelled and rejected ones stay listed but count for
        nothing. """
        return self.payment_ids.filtered(lambda payment: payment.state not in ('canceled', 'rejected'))

    def _om_payments_to_match(self):
        """ The payments of the batch the bank has not cleared yet. """
        return self._om_active_payments().filtered(
            lambda payment: payment.state != 'draft' and not payment.om_is_cleared)

    # -------------------------------------------------------------------------
    # Checks
    # -------------------------------------------------------------------------

    def _om_check_payments(self):
        for batch in self:
            for payment in batch.payment_ids:
                if payment.journal_id != batch.journal_id:
                    raise UserError(_('The payment %(payment)s is not paid with the bank %(journal)s of the batch.',
                                      payment=payment.display_name, journal=batch.journal_id.display_name))
                if payment.payment_type != batch.batch_type:
                    raise UserError(_('The payment %s goes in the other direction than the batch.',
                                      payment.display_name))
                if payment.payment_method_line_id != batch.payment_method_line_id:
                    raise UserError(_(
                        'The payment %(payment)s uses the method %(method)s, the batch %(batch_method)s.',
                        payment=payment.display_name, method=payment.payment_method_line_id.display_name,
                        batch_method=batch.payment_method_line_id.display_name))
                if payment.currency_id != batch.currency_id:
                    raise UserError(_('The payment %(payment)s is in %(currency)s, the batch in %(batch_currency)s.',
                                      payment=payment.display_name, currency=payment.currency_id.name,
                                      batch_currency=batch.currency_id.name))

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_validate_batch(self):
        """ Post the draft payments, generate the file of the bank and lock the batch. """
        for batch in self:
            if batch.state != 'draft':
                raise UserError(_('The batch %s is already sent.', batch.name))
            if not batch._om_active_payments():
                raise UserError(_('Add the payments of the batch %s first.', batch.name))
            batch._om_check_payments()
            batch.payment_ids.filtered(lambda payment: payment.state == 'draft').action_post()
            if batch.layout_id:
                batch.layout_id._check_payments(batch._om_active_payments())
                batch._om_generate_file()
            batch._om_active_payments().write({'is_sent': True})
            batch.state = 'sent'
            # a batch of payments without journal entries already matched by the bank is reconciled
            batch._compute_state()
        return True

    def action_draft(self):
        for batch in self:
            if batch.state == 'draft':
                continue
            if any(batch._om_active_payments().mapped('om_is_cleared')):
                raise UserError(_(
                    'The bank already cleared payments of the batch %s: undo their reconciliation first.',
                    batch.name))
            batch.payment_ids.write({'is_sent': False})
            batch.state = 'draft'
        return True

    def action_generate_file(self):
        for batch in self:
            if not batch.layout_id:
                raise UserError(_('Choose the layout of the bank file of the batch %s first.', batch.name))
            batch.layout_id._check_payments(batch._om_active_payments())
            batch._om_generate_file()
        return True

    def _om_generate_file(self):
        self.ensure_one()
        content, filename = self.layout_id._generate_file(self)
        self.write({
            'export_file': base64.b64encode(content),
            'export_filename': filename,
            'export_date': fields.Datetime.now(),
        })
        self.message_post(
            body=_('Bank file generated with the layout %s.', self.layout_id.name),
            attachments=[(filename, content)],
        )

    def action_download_file(self):
        self.ensure_one()
        if not self.export_file:
            self.action_generate_file()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/account.batch.payment/%s/export_file/%s?download=true' % (
                self.id, self.export_filename),
            'target': 'download',
        }

    def action_print(self):
        return self.env.ref('om_account_batch_payment.action_report_batch_payment').report_action(self)

    def action_open_payments(self):
        self.ensure_one()
        return self.payment_ids._get_records_action(name=_('Payments of %s', self.name), context={'create': False})

    def action_open_statement_lines(self):
        self.ensure_one()
        return self.statement_line_ids._get_records_action(name=_('Bank Transactions of %s', self.name))
