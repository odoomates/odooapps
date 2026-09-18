from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import formatLang

from .account_budget_position import BUDGET_TYPES

# fields that cannot change once the budget is confirmed
LOCKED_BUDGET_FIELDS = {'name', 'date_from', 'date_to', 'company_id', 'line_ids'}
WARNING_LEVELS = {'none': 0, 'threshold': 1, 'exceeded': 2}


class AccountBudget(models.Model):
    _name = 'account.budget'
    _description = 'Budget'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char('Budget Name', required=True)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one('res.users', 'Responsible', default=lambda self: self.env.user)
    date_from = fields.Date('Start Date', required=True)
    date_to = fields.Date('End Date', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('cancel', 'Cancelled'),
        ('confirm', 'Confirmed'),
        ('validate', 'Validated'),
        ('done', 'Done')
    ], 'Status', default='draft', index=True, required=True, readonly=True, copy=False, tracking=True)
    line_ids = fields.One2many('account.budget.line', 'budget_id', 'Budget Lines', copy=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    expense_planned_amount = fields.Monetary('Planned Expenses', compute='_compute_totals')
    expense_theoretical_amount = fields.Monetary('Theoretical Expenses', compute='_compute_totals')
    expense_practical_amount = fields.Monetary('Actual Expenses', compute='_compute_totals')
    expense_achievement = fields.Float('Expenses Achievement', compute='_compute_totals')
    revenue_planned_amount = fields.Monetary('Planned Revenues', compute='_compute_totals')
    revenue_theoretical_amount = fields.Monetary('Theoretical Revenues', compute='_compute_totals')
    revenue_practical_amount = fields.Monetary('Actual Revenues', compute='_compute_totals')
    revenue_achievement = fields.Float('Revenues Achievement', compute='_compute_totals')
    is_over_budget = fields.Boolean(
        'Over Budget', compute='_compute_totals', search='_search_is_over_budget',
        help="At least one expense line spent more than its theoretical amount.")

    @api.depends('line_ids.planned_amount', 'line_ids.budget_type', 'line_ids.date_from', 'line_ids.date_to')
    def _compute_totals(self):
        # compute the amounts of every line at once
        self.line_ids.mapped('practical_amount')
        for budget in self:
            for budget_type, dummy in BUDGET_TYPES:
                lines = budget.line_ids.filtered(lambda line: line.budget_type == budget_type)
                planned = sum(lines.mapped('planned_amount'))
                theoretical = sum(lines.mapped('theoretical_amount'))
                practical = sum(lines.mapped('practical_amount'))
                budget[f'{budget_type}_planned_amount'] = planned
                budget[f'{budget_type}_theoretical_amount'] = theoretical
                budget[f'{budget_type}_practical_amount'] = practical
                budget[f'{budget_type}_achievement'] = practical / theoretical if theoretical else 0.0
            budget.is_over_budget = any(budget.line_ids.mapped('is_over_budget'))

    def _search_is_over_budget(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_('Operation not supported.'))
        over_budget_lines = self.env['account.budget.line'].search([('is_over_budget', '=', True)])
        in_operator = 'in' if (operator == '=') == value else 'not in'
        return [('id', in_operator, over_budget_lines.budget_id.ids)]

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_from > budget.date_to:
                raise ValidationError(_('The budget "%s" must start before it ends.', budget.name))

    def write(self, vals):
        if LOCKED_BUDGET_FIELDS & set(vals) and not self.env.context.get('budget_force_edit'):
            locked = self.filtered(lambda budget: budget.state != 'draft')
            if locked:
                raise UserError(_('Reset the budget "%s" to draft to change it.', locked[0].name))
        return super().write(vals)

    def _check_budget_manager(self):
        if not self.env.su and not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only accounting managers can approve, close or cancel budgets.'))

    def action_budget_confirm(self):
        self.write({'state': 'confirm'})

    def action_budget_draft(self):
        self.write({'state': 'draft'})

    def action_budget_validate(self):
        self._check_budget_manager()
        self.write({'state': 'validate'})

    def action_budget_cancel(self):
        self._check_budget_manager()
        self.write({'state': 'cancel'})

    def action_budget_done(self):
        self._check_budget_manager()
        self.write({'state': 'done'})

    def action_open_budget_report(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_account_budget.action_account_budget_line_analysis')
        action.update({
            'name': _('Budget Report: %s', self.name),
            'domain': [('budget_id', '=', self.id)],
            'context': {'search_default_group_position_id': True},
        })
        return action

    def action_open_copy_wizard(self):
        self.ensure_one()
        return {
            'name': _('Copy to Next Period'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.budget.copy',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_budget_id': self.id},
        }

    def action_open_split_wizard(self):
        self.ensure_one()
        return {
            'name': _('Split Lines by Period'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.budget.split',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_budget_id': self.id},
        }

    @staticmethod
    def _shift_date(day, delta):
        """ Move `day` by `delta`, keeping it on the last day of its month when it was. """
        shifted = day + delta
        if day == day + relativedelta(day=31):
            shifted += relativedelta(day=31)
        return shifted

    def copy_to_period(self, date_from, date_to=None, name=None):
        """ Copy the budget and its lines to the period starting on `date_from`. """
        self.ensure_one()
        if date_from.day == 1 and self.date_from.day == 1:
            delta = relativedelta(date_from, self.date_from)
        else:
            delta = relativedelta(days=(date_from - self.date_from).days)
        new_budget = self.copy({
            'name': name or _('%s (copy)', self.name),
            'date_from': date_from,
            'date_to': date_to or self._shift_date(self.date_to, delta),
            'line_ids': [(0, 0, {
                **line.copy_data()[0],
                'budget_id': False,
                'date_from': self._shift_date(line.date_from, delta),
                'date_to': self._shift_date(line.date_to, delta),
                'planned_date': line.planned_date and self._shift_date(line.planned_date, delta),
            }) for line in self.line_ids],
        })
        return new_budget

    @api.model
    def _cron_warn_budget_responsibles(self):
        """ Warn the responsible of validated budgets when an expense line reaches the warning
        threshold of its company, then when it goes over its planned amount. """
        lines = self.env['account.budget.line'].search([
            ('budget_state', '=', 'validate'), ('budget_type', '=', 'expense'), ('planned_amount', '>', 0),
        ])
        # the actual amounts depend on journal items which are not dependencies of the field
        lines.invalidate_recordset(['practical_amount'])
        exceeded_budgets = self.browse()
        for line in lines:
            consumed = line.practical_amount / line.planned_amount
            if consumed > 1:
                level = 'exceeded'
            elif consumed * 100 >= line.company_id.budget_warning_threshold:
                level = 'threshold'
            else:
                level = 'none'
            if WARNING_LEVELS[level] > WARNING_LEVELS[line.warning_level or 'none']:
                if level == 'exceeded':
                    exceeded_budgets |= line.budget_id
                elif line.budget_id.user_id:
                    line.budget_id.message_post(
                        body=_('%(line)s reached %(percent)s%% of its planned amount (%(practical)s of %(planned)s).',
                               line=line.name, percent=round(consumed * 100), practical=line.practical_amount,
                               planned=line.planned_amount),
                        partner_ids=line.budget_id.user_id.partner_id.ids,
                        message_type='notification', subtype_xmlid='mail.mt_comment',
                    )
            if level != line.warning_level:
                line.with_context(budget_force_edit=True).warning_level = level
        for budget in exceeded_budgets:
            budget._alert_budget_exceeded()

    def _get_budget_alert_user(self):
        self.ensure_one()
        return self.user_id or self.create_uid

    def _get_budget_exceeded_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(lambda line: line.warning_level == 'exceeded')

    def _get_budget_exceeded_table(self):
        """ The lines over budget, as an HTML table for the activity and the email. """
        self.ensure_one()
        rows = Markup().join(
            Markup('<tr><td>%s</td><td style="text-align: right;">%s</td><td style="text-align: right;">%s</td>'
                   '<td style="text-align: right;"><strong>%s</strong></td></tr>') % (
                line.position_id.name or line.analytic_account_id.name or line.name,
                formatLang(self.env, line.planned_amount, currency_obj=self.currency_id),
                formatLang(self.env, line.practical_amount, currency_obj=self.currency_id),
                formatLang(self.env, line.practical_amount - line.planned_amount, currency_obj=self.currency_id),
            )
            for line in self._get_budget_exceeded_lines()
        )
        header = Markup('<tr><th>%s</th><th style="text-align: right;">%s</th><th style="text-align: right;">%s</th>'
                        '<th style="text-align: right;">%s</th></tr>') % (
            _('Line'), _('Planned'), _('Spent'), _('Over by'))
        return Markup('<table class="table table-sm o_budget_exceeded_table"><thead>%s</thead><tbody>%s</tbody></table>') % (
            header, rows)

    def _alert_budget_exceeded(self):
        """ Assign a To-Do activity listing the lines over budget to the responsible (updating the open one, if
        any), log it in the chatter and, when the company asks for it, email the responsible. """
        self.ensure_one()
        user = self._get_budget_alert_user()
        table = self._get_budget_exceeded_table()
        activity_type = self.env.ref('om_account_budget.mail_activity_type_budget_exceeded')
        activity = self.activity_ids.filtered(lambda activity: activity.activity_type_id == activity_type)[:1]
        note = Markup('<p>%s</p>%s') % (_('These lines spent more than planned:'), table)
        if activity:
            activity.note = note
        else:
            self.activity_schedule(
                'om_account_budget.mail_activity_type_budget_exceeded',
                summary=_('Over budget: %s', self.name), note=note, user_id=user.id,
            )
        if self.company_id.budget_exceeded_email and user.partner_id.email:
            template = self.env.ref('om_account_budget.mail_template_budget_exceeded')
            template.send_mail(self.id, email_layout_xmlid='mail.mail_notification_light')
            body = _('%(user)s was emailed: some lines spent more than planned.', user=user.name)
        else:
            body = _('Some lines spent more than planned.')
        self.message_post(
            body=Markup('<p>%s</p>%s') % (body, table),
            message_type='notification', subtype_xmlid='mail.mt_note',
        )
