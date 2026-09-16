from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date

# lock date fields of the company set by each kind of closing
LOCK_FIELDS = {
    'none': (),
    'sale_purchase': ('sale_lock_date', 'purchase_lock_date'),
    'tax': ('tax_lock_date',),
    'fiscal': ('fiscalyear_lock_date',),
}


class AccountPeriodClosing(models.Model):
    _name = 'account.period.closing'
    _description = 'Period Closing'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'
    _check_company_auto = True

    name = fields.Char(compute='_compute_name', store=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    date_from = fields.Date(
        string='Start Date', required=True, tracking=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1) - relativedelta(months=1))
    date_to = fields.Date(
        string='End Date', required=True, tracking=True, compute='_compute_date_to', store=True, readonly=False,
        precompute=True)
    state = fields.Selection([('open', 'Open'), ('closed', 'Closed')], default='open', required=True, tracking=True)
    lock_type = fields.Selection(
        [('none', 'Do not lock'),
         ('sale_purchase', 'Lock the sales and purchases'),
         ('tax', 'Lock the taxes'),
         ('fiscal', 'Lock everything (except for the administrators)')],
        string='When Closed', required=True, default='fiscal', tracking=True,
        help="The lock date set on the company when the period is closed. The permanent lock is set from the "
             "lock dates of the company.")
    check_ids = fields.One2many('account.period.closing.check', 'closing_id', string='Checklist')
    blocking_count = fields.Integer(compute='_compute_counts')
    warning_count = fields.Integer(compute='_compute_counts')
    task_todo_count = fields.Integer(compute='_compute_counts')
    last_check_date = fields.Datetime(string='Checked On', readonly=True)
    closed_by_id = fields.Many2one('res.users', string='Closed By', readonly=True, copy=False)
    closed_on = fields.Datetime(readonly=True, copy=False)
    previous_lock_dates = fields.Json(readonly=True, copy=False)

    _company_period_uniq = models.Constraint(
        'unique(company_id, date_from)', 'This period is already being closed.')

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for closing in self:
            if not closing.date_from or not closing.date_to:
                closing.name = _('New Closing')
            elif closing.date_from.day == 1 and closing.date_to == closing.date_from + relativedelta(day=31):
                closing.name = format_date(self.env, closing.date_from, date_format='MMMM y')
            else:
                closing.name = '%s - %s' % (format_date(self.env, closing.date_from),
                                            format_date(self.env, closing.date_to))

    @api.depends('date_from')
    def _compute_date_to(self):
        for closing in self:
            closing.date_to = closing.date_from and closing.date_from + relativedelta(day=31)

    @api.depends('check_ids.status')
    def _compute_counts(self):
        for closing in self:
            statuses = closing.check_ids.mapped('status')
            closing.blocking_count = statuses.count('blocking')
            closing.warning_count = statuses.count('warning')
            closing.task_todo_count = statuses.count('todo')

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_period(self):
        for closing in self:
            if closing.date_from > closing.date_to:
                raise ValidationError(_('The start date of the closing must be before its end date.'))
            if self.search_count([
                ('id', '!=', closing.id), ('company_id', '=', closing.company_id.id),
                ('date_from', '<=', closing.date_to), ('date_to', '>=', closing.date_from),
            ], limit=1):
                raise ValidationError(_('The period %s overlaps another closing.', closing.name))

    @api.model_create_multi
    def create(self, vals_list):
        closings = super().create(vals_list)
        for closing in closings:
            tasks = self.env['account.period.closing.task'].search([
                '|', ('company_id', '=', False), ('company_id', '=', closing.company_id.id)])
            closing.check_ids = [fields.Command.create({
                'sequence': 100 + task.sequence,
                'name': task.name,
                'note': task.note,
                'responsible_id': task.responsible_id.id,
                'is_manual': True,
            }) for task in tasks]
        closings.action_refresh()
        return closings

    def unlink(self):
        if self.filtered(lambda closing: closing.state == 'closed'):
            raise UserError(_('Reopen a closed period before deleting it.'))
        return super().unlink()

    # -------------------------------------------------------------------------
    # Automatic checks
    # -------------------------------------------------------------------------

    def _get_closing_checks(self):
        """ The automatic checks of the closing. Other modules add theirs.

        :return: list of dictionaries with `code`, `name`, `sequence`, `level` ('blocking' or 'warning'),
                 `model` and `domain` (the records to deal with, counted by the check)
        """
        self.ensure_one()
        company = self.company_id
        date_to = self.date_to
        checks = [{
            'code': 'draft_entries',
            'name': _('Draft entries dated up to the end of the period'),
            'sequence': 10,
            'level': 'blocking',
            'model': 'account.move',
            'domain': [('company_id', 'child_of', company.id), ('state', '=', 'draft'), ('date', '<=', date_to)],
        }, {
            'code': 'unreconciled_bank',
            'name': _('Bank transactions not reconciled'),
            'sequence': 20,
            # the global lock is refused while there are some
            'level': 'blocking' if self.lock_type == 'fiscal' else 'warning',
            'model': 'account.bank.statement.line',
            'domain': company._get_unreconciled_statement_lines_domain(date_to),
        }]
        transit_accounts = self._get_transit_accounts()
        if transit_accounts:
            checks.append({
                'code': 'transit_items',
                'name': _('Payments and suspense items not matched'),
                'sequence': 30,
                'level': 'warning',
                'model': 'account.move.line',
                'domain': [
                    ('company_id', 'child_of', company.id), ('account_id', 'in', transit_accounts.ids),
                    ('parent_state', '=', 'posted'), ('reconciled', '=', False), ('date', '<=', date_to),
                ],
            })
        negative_accounts = self._get_negative_cash_accounts()
        checks.append({
            'code': 'negative_cash',
            'name': _('Bank and cash accounts with a negative balance'),
            'sequence': 40,
            'level': 'warning',
            'model': 'account.move.line',
            'domain': [
                ('company_id', 'child_of', company.id), ('account_id', 'in', negative_accounts.ids),
                ('parent_state', '=', 'posted'), ('date', '<=', date_to),
            ],
            'count': len(negative_accounts),
        })
        duplicates = self._get_duplicate_bills()
        checks.append({
            'code': 'duplicate_bills',
            'name': _('Bills that might be duplicates'),
            'sequence': 50,
            'level': 'warning',
            'model': 'account.move',
            'domain': [('id', 'in', duplicates.ids)],
        })
        return checks

    def _get_transit_accounts(self):
        company = self.company_id
        journals = self.env['account.journal'].sudo().search([('company_id', 'child_of', company.id)])
        method_lines = self.env['account.payment.method.line'].sudo().search([('journal_id', 'in', journals.ids)])
        return (company.account_journal_suspense_account_id | company.transfer_account_id
                | journals.suspense_account_id | method_lines.payment_account_id).sudo(False)

    def _get_negative_cash_accounts(self):
        groups = self.env['account.move.line']._read_group(
            [('company_id', 'child_of', self.company_id.id), ('account_id.account_type', '=', 'asset_cash'),
             ('parent_state', '=', 'posted'), ('date', '<=', self.date_to)],
            groupby=['account_id'], aggregates=['balance:sum'])
        currency = self.company_id.currency_id
        return self.env['account.account'].browse([
            account.id for account, balance in groups if currency.compare_amounts(balance, 0.0) < 0])

    def _get_duplicate_bills(self):
        bills = self.env['account.move'].search([
            ('company_id', 'child_of', self.company_id.id), ('move_type', 'in', ('in_invoice', 'in_refund')),
            ('state', 'in', ('draft', 'posted')), ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ])
        return bills.filtered('duplicated_ref_ids')

    def action_refresh(self):
        """ Count again the records of the automatic checks. """
        for closing in self.filtered(lambda closing: closing.state == 'open'):
            existing = {check.code: check for check in closing.check_ids if not check.is_manual}
            commands = []
            codes = set()
            for definition in closing._get_closing_checks():
                codes.add(definition['code'])
                count = definition.get('count')
                if count is None:
                    count = self.env[definition['model']].search_count(definition['domain'])
                values = {
                    'code': definition['code'],
                    'name': definition['name'],
                    'sequence': definition['sequence'],
                    'level': definition['level'],
                    'count': count,
                }
                if definition['code'] in existing:
                    commands.append(fields.Command.update(existing[definition['code']].id, values))
                else:
                    commands.append(fields.Command.create(values))
            commands += [fields.Command.delete(check.id) for code, check in existing.items() if code not in codes]
            closing.write({'check_ids': commands, 'last_check_date': fields.Datetime.now()})
        return True

    def _open_check(self, code):
        self.ensure_one()
        definition = next((d for d in self._get_closing_checks() if d['code'] == code), None)
        if not definition:
            raise UserError(_('This check no longer exists, refresh the checklist.'))
        return {
            'name': definition['name'],
            'type': 'ir.actions.act_window',
            'res_model': definition['model'],
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': definition['domain'],
            'context': {'create': False},
        }

    # -------------------------------------------------------------------------
    # Closing
    # -------------------------------------------------------------------------

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only accounting administrators can close or reopen a period.'))

    def action_close(self):
        self._check_manager()
        for closing in self:
            if closing.state == 'closed':
                continue
            closing.action_refresh()
            blocking = closing.check_ids.filtered(lambda check: check.status == 'blocking')
            if blocking:
                raise UserError(_('Deal with these points before closing %(period)s:\n%(points)s',
                                  period=closing.name,
                                  points='\n'.join('- %s (%s)' % (check.name, check.count) for check in blocking)))
            todo = closing.check_ids.filtered(lambda check: check.status == 'todo')
            if todo:
                raise UserError(_('Mark these tasks as done before closing %(period)s:\n%(tasks)s',
                                  period=closing.name, tasks='\n'.join('- %s' % name for name in todo.mapped('name'))))
            company = closing.company_id
            previous = {}
            new_locks = {}
            for field_name in LOCK_FIELDS[closing.lock_type]:
                previous[field_name] = fields.Date.to_string(company[field_name]) if company[field_name] else False
                if not company[field_name] or company[field_name] < closing.date_to:
                    new_locks[field_name] = closing.date_to
            if new_locks:
                company.sudo().write(new_locks)
            closing.write({
                'state': 'closed',
                'closed_by_id': self.env.user.id,
                'closed_on': fields.Datetime.now(),
                'previous_lock_dates': previous,
            })
            closing.message_post(body=_('Period closed.') if not new_locks else _(
                'Period closed, locked until %s.', format_date(self.env, closing.date_to)))
        return True

    def action_reopen(self):
        """ Open the period again. The lock dates set by the closing go back to their previous value, unless they
        were changed since or a later period is closed. """
        self._check_manager()
        for closing in self.filtered(lambda closing: closing.state == 'closed'):
            if self.search_count([('company_id', '=', closing.company_id.id), ('state', '=', 'closed'),
                                  ('date_from', '>', closing.date_to)], limit=1):
                raise UserError(_('Reopen the later closed periods first.'))
            company = closing.company_id
            restore = {}
            for field_name, value in (closing.previous_lock_dates or {}).items():
                if company[field_name] == closing.date_to:
                    restore[field_name] = fields.Date.to_date(value) if value else False
            if restore:
                company.sudo().write(restore)
            if company.hard_lock_date and company.hard_lock_date >= closing.date_from:
                closing.message_post(body=_('The period stays locked: it is before the permanent lock date.'))
            closing.write({'state': 'open', 'closed_by_id': False, 'closed_on': False, 'previous_lock_dates': False})
            closing.message_post(body=_('Period reopened.'))
            closing.action_refresh()
        return True


class AccountPeriodClosingCheck(models.Model):
    _name = 'account.period.closing.check'
    _description = 'Period Closing Check'
    _order = 'sequence, id'

    closing_id = fields.Many2one('account.period.closing', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    code = fields.Char(readonly=True)
    name = fields.Char(required=True)
    note = fields.Text()
    is_manual = fields.Boolean(string='Task', readonly=True)
    level = fields.Selection([('blocking', 'Blocking'), ('warning', 'Warning')], default='warning', readonly=True)
    count = fields.Integer(readonly=True)
    responsible_id = fields.Many2one('res.users', string='Responsible')
    done = fields.Boolean(readonly=True)
    done_by_id = fields.Many2one('res.users', string='Done By', readonly=True)
    done_on = fields.Datetime(readonly=True)
    status = fields.Selection(
        [('ok', 'OK'), ('warning', 'Warning'), ('blocking', 'Blocking'), ('todo', 'To Do'), ('done', 'Done')],
        compute='_compute_status', store=True)

    @api.depends('is_manual', 'done', 'count', 'level')
    def _compute_status(self):
        for check in self:
            if check.is_manual:
                check.status = 'done' if check.done else 'todo'
            else:
                check.status = check.level if check.count else 'ok'

    def action_open(self):
        self.ensure_one()
        return self.closing_id._open_check(self.code)

    def action_mark_done(self):
        for check in self.filtered('is_manual'):
            if check.closing_id.state == 'closed':
                raise UserError(_('The period %s is closed.', check.closing_id.name))
            check.write({'done': True, 'done_by_id': self.env.user.id, 'done_on': fields.Datetime.now()})
        return True

    def action_mark_todo(self):
        for check in self.filtered('is_manual'):
            if check.closing_id.state == 'closed':
                raise UserError(_('The period %s is closed.', check.closing_id.name))
            check.write({'done': False, 'done_by_id': False, 'done_on': False})
        return True


class AccountPeriodClosingTask(models.Model):
    _name = 'account.period.closing.task'
    _description = 'Period Closing Task'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    note = fields.Text(translate=True)
    responsible_id = fields.Many2one('res.users', string='Responsible')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
