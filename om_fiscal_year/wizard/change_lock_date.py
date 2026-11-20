from odoo import models, fields, api, SUPERUSER_ID, _
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.misc import format_date

# the lock dates of the wizard, as on the company
LOCK_DATE_FIELDS = ('period_lock_date', 'fiscalyear_lock_date', 'tax_lock_date')


class ChangeLockDate(models.TransientModel):
    _name = 'change.lock.date'
    _description = 'Change Lock Date'

    @api.model
    def default_get(self, vals):
        res = super().default_get(vals)
        company_rec = self.env.company
        res.update({
            'company_id': company_rec.id,
            'period_lock_date': company_rec.period_lock_date,
            'fiscalyear_lock_date': company_rec.fiscalyear_lock_date,
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
    period_lock_date = fields.Date(
        string='Journal Entries Lock Date',
        help='Prevent posting of journal entries in this period.'
    )
    fiscalyear_lock_date = fields.Date(
        string='Lock Date for All Users',
        default=lambda self: self.env.company.fiscalyear_lock_date,
        help='No users, including Advisers, can edit accounts prior to and inclusive of '
             'this date. Use it for fiscal year locking.'
    )

    # what the new dates would leave behind
    draft_move_ids = fields.Many2many('account.move', compute='_compute_warnings')
    draft_warning = fields.Char(compute='_compute_warnings')
    tax_closing_warning = fields.Char(compute='_compute_warnings')

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
            domains = []
            for field, date in wizard._closed_lock_dates().items():
                domain = [('date', '<=', date)]
                if field == 'tax_lock_date':
                    domain.append(('line_ids.tax_line_id', '!=', False))
                domains.append(domain)
            drafts = AccountMove
            if domains:
                drafts = AccountMove.search(expression.AND([
                    [('company_id', '=', wizard.company_id.id), ('state', '=', 'draft')],
                    expression.OR(domains),
                ]))
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
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.draft_move_ids.ids)],
            'context': {'create': False},
        }

    def update_lock_date(self):
        self.ensure_one()
        has_manager_group = self.env.user.has_group('account.group_account_manager')
        if not (has_manager_group or self.env.uid == SUPERUSER_ID):
            raise UserError(_("You Are Not Allowed To Perform This Operation"))
        if self.env.uid != SUPERUSER_ID and self.company_id not in self.env.user.company_ids:
            raise UserError(_("You cannot change the lock dates of another company."))
        # sudo() is required because setting lock dates writes on res.company,
        # which accounting managers are not allowed to write on.
        self.company_id.sudo().write({
            'period_lock_date': self.period_lock_date,
            'fiscalyear_lock_date': self.fiscalyear_lock_date,
            'tax_lock_date': self.tax_lock_date,
        })
