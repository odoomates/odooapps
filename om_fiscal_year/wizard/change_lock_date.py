from datetime import timedelta

from markupsafe import Markup

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.misc import format_date, format_datetime

from odoo.addons.account.models.company import LOCK_DATE_FIELDS, SOFT_LOCK_DATE_FIELDS

# how long an exception to a lock date lasts
EXCEPTION_DURATIONS = {
    '5min': timedelta(minutes=5),
    '15min': timedelta(minutes=15),
    '1h': timedelta(hours=1),
    '24h': timedelta(hours=24),
    'forever': None,
}


class ChangeLockDate(models.TransientModel):
    """ Set the lock dates of the company. A date set or moved forward is written on the company; a soft lock date
    removed or moved back is not: an exception to it is created instead, for a time, for the user or everyone, with
    its reason, as Odoo logs the exceptions in the chatter of the company. """
    _name = 'change.lock.date'
    _description = 'Change Lock Date'

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        company_rec = self.env.company
        res.update({
            'company_id': company_rec.id,
            'hard_lock_date': company_rec.hard_lock_date,
            'fiscalyear_lock_date': company_rec.fiscalyear_lock_date,
            'purchase_lock_date': company_rec.purchase_lock_date,
            'sale_lock_date': company_rec.sale_lock_date,
            'tax_lock_date': company_rec.tax_lock_date,
        })
        return res

    company_id = fields.Many2one(
        'res.company', string="Company",
        required=True, default=lambda self: self.env.company
    )
    tax_lock_date = fields.Date(
        string="Tax Return Lock Date",
        help="No users can edit journal entries related to a tax prior and inclusive of this date.")
    sale_lock_date = fields.Date(
        string='Sales Lock Date',
        help='Prevents creation and modification of entries in sales journals up to the defined date inclusive.'
    )
    purchase_lock_date = fields.Date(
        string='Purchase Lock date',
        help='Prevents creation and modification of entries in purchase journals up to the defined date inclusive.'
    )
    hard_lock_date = fields.Date(
        string='Hard Lock Date',
        help='Like the "Global Lock Date", but no exceptions are possible.'
    )
    fiscalyear_lock_date = fields.Date(
        string='Global Lock Date',
        default=lambda self: self.env.company.fiscalyear_lock_date,
        help='No users, including Advisers, can edit accounts prior to and inclusive of '
             'this date. Use it for fiscal year locking.'
    )
    exception_needed = fields.Boolean(
        compute='_compute_exception_needed',
        help='A lock date is removed or moved back: an exception to it is created, the company keeps its date.')
    exception_fields = fields.Char(compute='_compute_exception_needed', string='Lock Dates Opened')
    exception_applies_to = fields.Selection(
        [('me', 'Only Me'), ('everyone', 'Everyone')], string='Exception For', required=True, default='me')
    exception_duration = fields.Selection(
        [('5min', '5 Minutes'), ('15min', '15 Minutes'), ('1h', '1 Hour'), ('24h', '24 Hours'),
         ('forever', 'Forever')], string='During', required=True, default='5min')
    exception_reason = fields.Char(string='Reason',
                                   help='Why the period is opened: logged in the chatter of the company.')

    # what is already open, and what the new dates would leave behind
    exceptions_for_me = fields.Html(compute='_compute_exceptions', sanitize=False)
    exceptions_for_everyone = fields.Html(compute='_compute_exceptions', sanitize=False)
    draft_move_ids = fields.Many2many('account.move', compute='_compute_warnings')
    draft_warning = fields.Char(compute='_compute_warnings')
    tax_closing_warning = fields.Char(compute='_compute_warnings')

    @api.depends('company_id')
    def _compute_exceptions(self):
        for wizard in self:
            exceptions = self.env['account.lock_exception'].search([
                ('company_id', '=', wizard.company_id.id), ('state', '=', 'active')], order='create_date desc')
            wizard.exceptions_for_me = wizard._exceptions_html(
                exceptions.filtered(lambda exception: exception.user_id == self.env.user))
            wizard.exceptions_for_everyone = wizard._exceptions_html(
                exceptions.filtered(lambda exception: not exception.user_id))

    def _exceptions_html(self, exceptions):
        if not exceptions:
            return False
        labels = dict(self.env['account.lock_exception']._fields['lock_date_field']._description_selection(self.env))
        rows = Markup('').join(
            Markup('<li>%s</li>') % _(
                '%(lock)s opened to %(date)s, %(until)s: %(reason)s',
                lock=labels.get(exception.lock_date_field, exception.lock_date_field),
                date=format_date(self.env, exception.lock_date) if exception.lock_date else _('no date'),
                until=_('until %s', format_datetime(self.env, exception.end_datetime)) if exception.end_datetime
                else _('for good'),
                reason=exception.reason or '')
            for exception in exceptions)
        return Markup('<ul class="mb-0">%s</ul>') % rows

    def _closed_lock_dates(self):
        """ :return: {lock date field: new date} of the lock dates the wizard sets or moves forward """
        self.ensure_one()
        company = self.company_id
        return {field: self[field] for field in LOCK_DATE_FIELDS
                if self[field] and (not company[field] or self[field] > company[field])}

    @api.depends('company_id', *LOCK_DATE_FIELDS)
    def _compute_warnings(self):
        AccountMove = self.env['account.move']
        for wizard in self:
            closed = wizard._closed_lock_dates()
            domains = []
            for field, date in closed.items():
                domain = [('date', '<=', date)]
                if field == 'sale_lock_date':
                    domain.append(('journal_id.type', '=', 'sale'))
                elif field == 'purchase_lock_date':
                    domain.append(('journal_id.type', '=', 'purchase'))
                elif field == 'tax_lock_date':
                    domain.append(('line_ids.tax_line_id', '!=', False))
                domains.append(domain)
            drafts = AccountMove
            if domains:
                drafts = AccountMove.search(
                    Domain('company_id', '=', wizard.company_id.id) & Domain('state', '=', 'draft')
                    & Domain.OR(domains))
            wizard.draft_move_ids = drafts
            wizard.draft_warning = _(
                '%s draft entries are dated in the period being locked: they cannot be posted once it is locked.',
                len(drafts)) if drafts else False
            wizard.tax_closing_warning = wizard._tax_closing_warning()

    def _tax_closing_warning(self):
        """ A warning when tax closings are posted after the tax lock date: the periods they close can still
        change. A tax closing is an entry clearing the tax accounts, without taxes of its own. """
        self.ensure_one()
        lock_date = self.tax_lock_date or self.company_id.tax_lock_date
        tax_accounts = self.env['account.tax.repartition.line'].search([
            ('company_id', '=', self.company_id.id), ('account_id', '!=', False)]).account_id
        if not tax_accounts:
            return False
        domain = [
            ('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted'),
            ('move_id.move_type', '=', 'entry'), ('account_id', 'in', tax_accounts.ids),
            ('tax_line_id', '=', False), ('tax_ids', '=', False),
        ]
        if lock_date:
            domain.append(('date', '>', lock_date))
        closings = self.env['account.move.line'].search(domain).move_id.filtered(
            lambda move: not move.line_ids.tax_ids and not move.line_ids.tax_line_id)
        if not closings:
            return False
        last = max(closings.mapped('date'))
        return _('A tax closing is posted on %(date)s, after the tax lock date: set the tax lock date to %(date)s so '
                 'that the periods closed cannot change any more.', date=format_date(self.env, last))

    def action_open_draft_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Draft Entries to Post or Delete'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.draft_move_ids.ids)],
            'context': {'create': False},
        }

    @api.depends('company_id', *SOFT_LOCK_DATE_FIELDS)
    def _compute_exception_needed(self):
        for wizard in self:
            opened = wizard._opened_lock_dates()
            wizard.exception_needed = bool(opened)
            wizard.exception_fields = wizard._lock_date_labels(opened) or False

    def _lock_date_labels(self, lock_date_fields):
        """ :return: the labels of the lock dates, e.g. 'Global Lock Date and Tax Return Lock Date' """
        labels = [self._fields[field]._description_string(self.env) for field in lock_date_fields]
        if len(labels) < 2:
            return ''.join(labels)
        return _('%(dates)s and %(last)s', dates=', '.join(labels[:-1]), last=labels[-1])

    def _opened_lock_dates(self):
        """ :return: the soft lock dates the wizard removes or moves back from the dates of the company """
        self.ensure_one()
        company = self.company_id
        return [field for field in SOFT_LOCK_DATE_FIELDS
                if company[field] and (not self[field] or self[field] < company[field])]

    def _changed_lock_dates(self):
        """ :return: the lock dates the user changed; the others are not written again """
        self.ensure_one()
        return [field for field in LOCK_DATE_FIELDS if self[field] != self.company_id[field]]

    def action_remove_lock_date(self):
        """ Remove a soft lock date from the wizard, as clearing the field does, and show it again with the panel
        of the exception: reopening a period does not depend on how the date widget can be emptied. """
        self.ensure_one()
        field = self.env.context.get('lock_date_field')
        if field not in SOFT_LOCK_DATE_FIELDS:
            raise UserError(_('Only the soft lock dates can be removed: the hard lock date cannot be undone.'))
        self[field] = False
        action = self.env['ir.actions.act_window']._for_xml_id('om_fiscal_year.action_view_change_lock_date')
        action['res_id'] = self.id
        return action

    def update_lock_date(self):
        self.ensure_one()
        has_manager_group = self.env.user.has_group('account.group_account_manager')
        if not (has_manager_group or self.env.uid == SUPERUSER_ID):
            raise UserError(_("You Are Not Allowed To Perform This Operation"))
        if self.env.uid != SUPERUSER_ID and self.company_id not in self.env.user.company_ids:
            raise UserError(_("You cannot change the lock dates of another company."))
        opened = self._opened_lock_dates()
        if opened and not (self.exception_reason or '').strip():
            raise UserError(_('Fill in the Reason field to reopen the %s. It says why the period is reopened '
                              'and is logged with the exception.', self.exception_fields))
        # sudo() is required because setting lock dates writes on res.company,
        # which accounting managers are not allowed to write on.
        values = {field: self[field] for field in self._changed_lock_dates() if field not in opened}
        if values:
            self.company_id.sudo().write(values)
        if opened:
            self._create_exceptions(opened)

    def _create_exceptions(self, lock_date_fields):
        """ An exception to each lock date opened, instead of changing the date of the company. """
        self.ensure_one()
        duration = EXCEPTION_DURATIONS[self.exception_duration]
        # as the user, not as the super user: the chatter of the company tells who opened the period
        self.env['account.lock_exception'].create([{
            'company_id': self.company_id.id,
            field: self[field],
            'user_id': self.env.user.id if self.exception_applies_to == 'me' else False,
            'end_datetime': fields.Datetime.now() + duration if duration else False,
            'reason': self.exception_reason.strip(),
        } for field in lock_date_fields])
