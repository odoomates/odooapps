from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError

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
    def default_get(self, vals):
        res = super().default_get(vals)
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
        string='Lock Date for All Users',
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

    @api.depends('company_id', *SOFT_LOCK_DATE_FIELDS)
    def _compute_exception_needed(self):
        for wizard in self:
            opened = wizard._opened_lock_dates()
            wizard.exception_needed = bool(opened)
            wizard.exception_fields = ', '.join(
                wizard._fields[field]._description_string(self.env) for field in opened) or False

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

    def update_lock_date(self):
        self.ensure_one()
        has_manager_group = self.env.user.has_group('account.group_account_manager')
        if not (has_manager_group or self.env.uid == SUPERUSER_ID):
            raise UserError(_("You Are Not Allowed To Perform This Operation"))
        if self.env.uid != SUPERUSER_ID and self.company_id not in self.env.user.company_ids:
            raise UserError(_("You cannot change the lock dates of another company."))
        opened = self._opened_lock_dates()
        if opened and not (self.exception_reason or '').strip():
            raise UserError(_('Tell why %s are opened: the reason is logged with the exception.',
                              self.exception_fields))
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
