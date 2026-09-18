import logging

from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import LockError, UserError, ValidationError
from odoo.tools import format_date

_logger = logging.getLogger(__name__)


class RecurringPayment(models.Model):
    _name = 'recurring.payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Recurring Payment'
    _rec_name = 'name'
    _check_company_auto = True

    name = fields.Char('Name', readonly=True)
    partner_id = fields.Many2one('res.partner', string="Partner", required=True, check_company=True, tracking=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user,
                              domain="[('share', '=', False)]", tracking=True,
                              help="Warned when a payment of this recurring payment cannot be created.")
    company_id = fields.Many2one('res.company', string='Company',
                                 compute='_compute_company_id', store=True, readonly=False, precompute=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  compute='_compute_currency_id', store=True, readonly=False, precompute=True)
    amount = fields.Monetary(string="Amount", currency_field='currency_id', tracking=True)
    journal_id = fields.Many2one('account.journal', 'Journal', required=True, check_company=True,
                                 domain=[('type', 'in', ('bank', 'cash'))], tracking=True,
                                 compute='_compute_journal_id', store=True, readonly=False, precompute=True)
    payment_type = fields.Selection([
        ('outbound', 'Send Money'),
        ('inbound', 'Receive Money'),
    ], string='Payment Type', required=True, default='inbound', tracking=True)
    state = fields.Selection(selection=[('draft', 'Draft'),
                                        ('done', 'Done'),
                                        ('cancel', 'Stopped')], default='draft', string='Status', tracking=True)
    date_begin = fields.Date(string='Start Date', required=True, tracking=True)
    date_end = fields.Date(string='End Date', required=True, tracking=True)
    template_id = fields.Many2one('account.recurring.template', 'Recurring Template',
                                  domain=[('state', '=', 'done')], required=True, check_company=True, tracking=True)
    recurring_period = fields.Selection(related='template_id.recurring_period')
    recurring_interval = fields.Integer('Recurring Interval', related='template_id.recurring_interval')
    journal_state = fields.Selection(string='Generate Journal As', related='template_id.journal_state')

    description = fields.Text('Description')
    line_ids = fields.One2many('recurring.payment.line', 'recurring_payment_id', string='Recurring Lines')
    has_error = fields.Boolean('Payment Failed', compute='_compute_has_error', search='_search_has_error')

    @api.depends('line_ids.error_message')
    def _compute_has_error(self):
        for rec in self:
            rec.has_error = any(rec.line_ids.mapped('error_message'))

    def _search_has_error(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        failed = self.env['recurring.payment.line']._search([('error_message', '!=', False)])
        domain = [('line_ids', 'any', failed)]
        return domain if (operator == 'in') == (True in value) else ['!'] + domain

    @api.depends('template_id')
    def _compute_company_id(self):
        for rec in self:
            template = rec.template_id
            rec.company_id = template.company_id or template.journal_id.company_id or rec.company_id or self.env.company

    @api.depends('template_id')
    def _compute_journal_id(self):
        for rec in self:
            rec.journal_id = rec.template_id.journal_id

    @api.depends('journal_id', 'company_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.journal_id.currency_id or rec.company_id.currency_id or self.env.company.currency_id

    def compute_next_date(self, date):
        period = self.recurring_period
        interval = self.recurring_interval
        if period == 'days':
            date += relativedelta(days=interval)
        elif period == 'weeks':
            date += relativedelta(weeks=interval)
        elif period == 'months':
            date += relativedelta(months=interval)
        else:
            date += relativedelta(years=interval)
        return date

    def action_create_lines(self, date):
        ids = self.env['recurring.payment.line']
        vals = {
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'date': date,
            'recurring_payment_id': self.id,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'state': 'draft'
        }
        ids.create(vals)

    def action_done(self):
        for rec in self:
            if rec.recurring_interval <= 0:
                raise UserError(_('The recurring interval of template %s must be a positive number.',
                                  rec.template_id.display_name))
            date_begin = rec.date_begin
            while date_begin <= rec.date_end:
                date = date_begin
                rec.action_create_lines(date)
                date_begin = rec.compute_next_date(date)
            rec.state = 'done'

    def action_draft(self):
        for rec in self:
            if rec.line_ids.filtered(lambda t: t.state == 'done'):
                raise ValidationError(_('You cannot Set to Draft as one of the line is already in done state'))
            rec.line_ids.unlink()
            rec.state = 'draft'

    def action_stop(self):
        """ End the recurring payment early: the lines not paid yet are skipped. """
        for rec in self:
            rec.line_ids.filtered(lambda line: line.state == 'draft').write({'state': 'cancel', 'error_message': False})
            rec.state = 'cancel'
        self._close_failure_activities()

    def action_generate_payment(self):
        line_ids = self.env['recurring.payment.line'].search([
            ('date', '<=', fields.Date.context_today(self)),
            ('state', '=', 'draft'),
            ('recurring_payment_id.state', '=', 'done'),
        ], order='date, id')
        for line in line_ids:
            try:
                with self.env.cr.savepoint():
                    line.with_company(line.company_id).action_create_payment()
            except Exception as error:
                _logger.warning("Recurring payment line %s (%s) could not be paid: %s",
                                line.id, line.recurring_payment_id.name, error)
                line._notify_payment_error(error)

    def _failure_activity_type(self):
        return self.env.ref('om_recurring_payments.mail_activity_type_recurring_payment_failed',
                            raise_if_not_found=False)

    def _close_failure_activities(self):
        """ The warnings of the recurring payments with nothing failing any more are done """
        activity_type = self._failure_activity_type()
        if not activity_type:
            return
        solved = self.filtered(lambda rec: not rec.has_error)
        activities = solved.activity_ids.filtered(lambda activity: activity.activity_type_id == activity_type)
        if activities:
            activities.action_feedback(feedback=_('The payments are created again.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sequence = self.env['ir.sequence']
            if vals.get('company_id'):
                sequence = sequence.with_company(vals['company_id'])
            vals['name'] = sequence.next_by_code('recurring.payment') or _('New')
        return super().create(vals_list)

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_('Amount Must Be Non-Zero Positive Number'))

    @api.constrains('date_begin', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_begin > rec.date_end:
                raise ValidationError(_('The start date must be before the end date.'))

    def unlink(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(_('Cannot delete done records !'))
        return super().unlink()


class RecurringPaymentLine(models.Model):
    _name = 'recurring.payment.line'
    _description = 'Recurring Payment Line'
    _check_company_auto = True

    recurring_payment_id = fields.Many2one('recurring.payment', string="Recurring Payment")
    partner_id = fields.Many2one('res.partner', 'Partner', required=True, check_company=True)
    amount = fields.Monetary('Amount', required=True, default=0.0)
    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', 'Journal', required=True, check_company=True,
                                 domain=[('type', 'in', ('bank', 'cash'))])
    company_id = fields.Many2one('res.company', string='Company',
                                 compute='_compute_company_id', store=True, readonly=False, precompute=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  compute='_compute_currency_id', store=True, readonly=False, precompute=True)
    payment_id = fields.Many2one('account.payment', string='Payment')
    state = fields.Selection(selection=[('draft', 'Draft'),
                                        ('done', 'Done'),
                                        ('cancel', 'Skipped')], default='draft', string='Status')
    error_message = fields.Text('Error', readonly=True, copy=False,
                                help="Why the payment of this line could not be created on its date.")

    @api.depends('recurring_payment_id')
    def _compute_company_id(self):
        for line in self:
            line.company_id = line.recurring_payment_id.company_id or line.company_id or self.env.company

    @api.depends('recurring_payment_id', 'company_id')
    def _compute_currency_id(self):
        for line in self:
            line.currency_id = line.recurring_payment_id.currency_id or line.company_id.currency_id

    def action_create_payment(self):
        # a concurrent click or cron run holding the line makes this one fail instead of paying twice
        try:
            self.lock_for_update()
        except LockError:
            raise UserError(_('The payment of this line is already being created, please try again in a moment.'))
        for line in self:
            if line.state != 'draft':
                continue
            payment_type = line.recurring_payment_id.payment_type
            vals = {
                'payment_type': payment_type,
                'partner_type': 'supplier' if payment_type == 'outbound' else 'customer',
                'amount': line.amount,
                'currency_id': line.currency_id.id,
                'journal_id': line.journal_id.id,
                'company_id': line.company_id.id,
                'date': line.date,
                'memo': line.recurring_payment_id.name,
                'partner_id': line.partner_id.id,
            }
            payment = self.env['account.payment'].create(vals)
            if line.recurring_payment_id.journal_state == 'posted':
                payment.action_post()
            line.write({'state': 'done', 'payment_id': payment.id, 'error_message': False})
        self.recurring_payment_id._close_failure_activities()

    def _notify_payment_error(self, error):
        """ Keep why the payment failed on the line and warn the responsible of the recurring payment, once
        per new error. """
        self.ensure_one()
        message = str(error.args[0] if isinstance(error, (UserError, ValidationError)) and error.args else error)
        if self.error_message == message:
            return
        self.error_message = message
        recurring = self.recurring_payment_id
        body = _("The payment of %(date)s could not be created: %(error)s",
                 date=format_date(self.env, self.date), error=message)
        recurring.message_post(body=body)
        activity_type = recurring._failure_activity_type()
        if activity_type and not recurring.activity_ids.filtered(
                lambda activity: activity.activity_type_id == activity_type):
            recurring.activity_schedule(
                activity_type_id=activity_type.id,
                summary=_('Payment failed'),
                note=body,
                user_id=(recurring.user_id or recurring.create_uid).id,
            )

    def action_skip(self):
        for line in self:
            if line.state != 'draft':
                raise UserError(_('Only the lines not paid yet can be skipped.'))
            line.write({'state': 'cancel', 'error_message': False})
        self.recurring_payment_id._close_failure_activities()

    def action_reset(self):
        for line in self:
            if line.state != 'cancel' or line.recurring_payment_id.state != 'done':
                raise UserError(_('Only the skipped lines of a running recurring payment can be reset.'))
            line.state = 'draft'


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def unlink(self):
        # the recurring lines of deleted payments are due again
        lines = self.env['recurring.payment.line'].sudo().search([('payment_id', 'in', self.ids)])
        res = super().unlink()
        lines.write({'state': 'draft'})
        return res
