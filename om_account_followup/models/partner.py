from collections import defaultdict
from datetime import timedelta

from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import SQL
from odoo.tools.misc import format_date, formatLang

FOLLOWUP_STATUSES = [
    ('in_need_of_action', 'Action Needed'),
    ('with_overdue_invoices', 'Overdue'),
    ('promise', 'Promise to Pay'),
    ('excluded', 'Excluded'),
    ('no_action_needed', 'No Overdue'),
]

# the ageing of the open items, in days overdue
AGEING_BUCKETS = [
    ('not_due', 'Not Due', 0, 0),
    ('1_30', '1-30 Days', 1, 30),
    ('31_60', '31-60 Days', 31, 60),
    ('61_90', '61-90 Days', 61, 90),
    ('over_90', 'Over 90 Days', 91, None),
]


class ResPartner(models.Model):
    _inherit = "res.partner"

    # -------------------------------------------------------------------------
    # Fields
    # -------------------------------------------------------------------------

    payment_responsible_id = fields.Many2one(
        'res.users', ondelete='set null',
        string='Follow-up Responsible', tracking=True, copy=False,
        help="The user in charge of collecting the payments of this customer: the manual actions of the "
             "follow-ups are assigned to this user.")
    payment_note = fields.Text(
        'Customer Payment Promise', help="Payment Note", copy=False
    )
    # replaced by the activities of the customer, kept for the history
    payment_next_action = fields.Text('Next Action', copy=False)
    payment_next_action_date = fields.Date('Next Action Date', copy=False)
    unreconciled_aml_ids = fields.One2many(
        'account.move.line', 'partner_id',
        domain=[('full_reconcile_id', '=', False), ('account_id.account_type', '=', 'asset_receivable'),
                ('parent_state', '=', 'posted')]
    )
    latest_followup_date = fields.Date(
        compute='_get_latest', string="Latest Follow-up Date", compute_sudo=True,
        help="Latest date that the follow-up level of the partner was changed"
    )
    latest_followup_level_id = fields.Many2one(
        'followup.line', compute='_get_latest', compute_sudo=True,
        string="Latest Follow-up Level", help="The maximum follow-up level"
    )
    payment_amount_due = fields.Float(
        compute='_get_amounts_and_date',
        string="Amount Due", search='_payment_due_search'
    )
    payment_amount_overdue = fields.Float(
        compute='_get_amounts_and_date',
        string="Amount Overdue", search='_payment_overdue_search'
    )
    payment_earliest_due_date = fields.Date(
        compute='_get_amounts_and_date', string="Worst Due Date",
        search='_payment_earliest_date_search'
    )

    followup_plan_id = fields.Many2one(
        'followup.followup', string='Follow-up Plan', company_dependent=True, tracking=True,
        domain="[('company_id', '=', current_company_id)]",
        help="The reminders sent to this customer. Leave empty for the default plan of the company.")
    followup_excluded = fields.Boolean(
        string='Excluded from Follow-ups', company_dependent=True, tracking=True,
        help="No reminder is sent to this customer.")
    followup_exclusion_reason = fields.Char(string='Exclusion Reason', company_dependent=True, tracking=True)
    followup_promise_date = fields.Date(
        string='Promised Payment Date', company_dependent=True, tracking=True,
        help="The customer promised to pay by this date: no reminder is sent until then.")
    followup_promise_amount = fields.Float(
        string='Promised Amount', company_dependent=True, tracking=True, digits='Account')
    followup_status = fields.Selection(
        FOLLOWUP_STATUSES, string='Follow-up Status', compute='_compute_followup_status',
        search='_search_followup_status')
    followup_next_date = fields.Date(
        string='Next Reminder', compute='_compute_followup_status',
        help="The day the next reminder is due, from the due dates of the open invoices and the delays of the "
             "follow-up plan.")
    followup_level_due_id = fields.Many2one(
        'followup.line', string='Reminder Due', compute='_compute_followup_status',
        help="The level of the reminder to send now.")
    followup_currency_id = fields.Many2one('res.currency', compute='_compute_followup_currency')

    # -------------------------------------------------------------------------
    # Follow-up engine
    # -------------------------------------------------------------------------

    def _followup_plan(self):
        """ :return: the plan of the customer in the current company """
        self.ensure_one()
        return self.followup_plan_id or self.env['followup.followup']._get_default_plan()

    def _followup_state(self, date=None):
        """ Where each customer stands in its follow-up plan, in the current company.

        Each open item has reached a level of the plan (none at first). The next level is due once the item is
        overdue by the delay of that level; the reminder due for the customer is the highest level due among its
        items.

        :return: {partner: {'lines_due': {line: level}, 'level_due': level, 'next_date': date,
                            'amount_due': float, 'amount_overdue': float}}
        """
        date = date or fields.Date.context_today(self)
        company = self.env.company
        lines = self.env['account.move.line'].sudo().search(
            self.env['account.move.line']._followup_open_domain(company, self))
        lines_by_partner = defaultdict(lambda: self.env['account.move.line'].sudo())
        for line in lines:
            lines_by_partner[line.partner_id.id] |= line
        state = {}
        levels_by_plan = {}
        for partner in self:
            plan = partner._followup_plan()
            if plan not in levels_by_plan:
                levels_by_plan[plan] = plan._get_levels() if plan else self.env['followup.line']
            levels = levels_by_plan[plan]
            lines_due = {}
            next_date = False
            amount_due = amount_overdue = 0.0
            for line in lines_by_partner[partner.id]:
                amount_due += line.amount_residual
                if line._followup_due_date() <= date:
                    amount_overdue += line.amount_residual
                if line.amount_residual <= 0:
                    continue
                current = line.followup_line_id if line.followup_line_id in levels else None
                following = levels.filtered(lambda level: not current or level.delay > current.delay)[:1]
                if not following:
                    continue
                due_on = line._followup_due_date() + timedelta(days=following.delay)
                if due_on <= date:
                    # an item late on several levels goes to the highest one reached
                    reached = levels.filtered(
                        lambda level: (not current or level.delay > current.delay)
                        and line._followup_due_date() + timedelta(days=level.delay) <= date)
                    lines_due[line] = reached[-1]
                    due_on = date
                if not next_date or due_on < next_date:
                    next_date = due_on
            level_due = max(lines_due.values(), key=lambda level: level.delay) if lines_due else \
                self.env['followup.line']
            state[partner] = {
                'lines_due': lines_due,
                'level_due': level_due,
                'next_date': next_date,
                'amount_due': amount_due,
                'amount_overdue': amount_overdue,
            }
        return state

    def _followup_status_of(self, values, today):
        self.ensure_one()
        if self.followup_excluded:
            return 'excluded'
        if values['amount_due'] <= 0:
            return 'no_action_needed'
        if self.followup_promise_date and self.followup_promise_date >= today:
            return 'promise'
        if values['lines_due']:
            return 'in_need_of_action'
        if values['amount_overdue'] > 0:
            return 'with_overdue_invoices'
        return 'no_action_needed'

    @api.depends_context('company')
    def _compute_followup_status(self):
        today = fields.Date.context_today(self)
        partners = self.filtered('id')
        state = partners._followup_state(today)
        for partner in self:
            values = state.get(partner)
            if not values:
                partner.followup_status = 'excluded' if partner.followup_excluded else 'no_action_needed'
                partner.followup_next_date = False
                partner.followup_level_due_id = False
                continue
            partner.followup_status = partner._followup_status_of(values, today)
            partner.followup_next_date = values['next_date']
            partner.followup_level_due_id = values['level_due']

    def _search_followup_status(self, operator, value):
        if operator not in ('in', '='):
            return NotImplemented
        values = {value} if operator == '=' else set(value)
        company = self.env.company
        self.env.flush_all()
        self.env.cr.execute(SQL("""
            SELECT DISTINCT line.partner_id
              FROM account_move_line line
              JOIN account_account account ON account.id = line.account_id
              JOIN account_move move ON move.id = line.move_id
             WHERE line.company_id = %s
               AND account.account_type = 'asset_receivable'
               AND line.parent_state = 'posted'
               AND NOT line.reconciled
               AND line.amount_residual != 0
               AND line.partner_id IS NOT NULL
               AND NOT COALESCE(move.followup_disputed, FALSE)
        """, company.id))
        with_items = self.browse([row[0] for row in self.env.cr.fetchall()])
        excluded = self.with_context(active_test=False).search([('followup_excluded', '=', True)])
        today = fields.Date.context_today(self)
        state = with_items._followup_state(today)
        matching = [partner.id for partner in with_items
                    if partner._followup_status_of(state[partner], today) in values]
        if 'excluded' in values:
            matching += excluded.ids
        if 'no_action_needed' in values:
            # the customers with nothing open, unless they are excluded
            return ['|', ('id', 'in', matching), ('id', 'not in', (with_items | excluded).ids)]
        return [('id', 'in', matching)]

    @api.depends_context('company')
    def _compute_followup_currency(self):
        for partner in self:
            partner.followup_currency_id = self.env.company.currency_id

    # -------------------------------------------------------------------------
    # Amounts
    # -------------------------------------------------------------------------

    @api.depends_context('company')
    def _get_latest(self):
        company = self.env.company
        for partner in self:
            latest_date = False
            latest_level = self.env['followup.line']
            for aml in partner.unreconciled_aml_ids:
                if aml.company_id != company:
                    continue
                if aml.followup_line_id and (not latest_level or latest_level.delay < aml.followup_line_id.delay):
                    latest_level = aml.followup_line_id
                if aml.followup_date and (not latest_date or latest_date < aml.followup_date):
                    latest_date = aml.followup_date
            partner.latest_followup_date = latest_date
            partner.latest_followup_level_id = latest_level

    @api.depends_context('company')
    def _get_amounts_and_date(self):
        company = self.env.company
        current_date = fields.Date.context_today(self)
        for partner in self:
            worst_due_date = False
            amount_due = amount_overdue = 0.0
            for aml in partner.unreconciled_aml_ids:
                if aml.company_id != company or aml.move_id.followup_disputed:
                    continue
                date_maturity = aml.date_maturity or aml.date
                if not worst_due_date or date_maturity < worst_due_date:
                    worst_due_date = date_maturity
                amount_due += aml.result
                if date_maturity <= current_date:
                    amount_overdue += aml.result
            partner.payment_amount_due = amount_due
            partner.payment_amount_overdue = amount_overdue
            partner.payment_earliest_due_date = worst_due_date

    def _followup_having_condition(self, expression, operator, value):
        """ SQL condition comparing the aggregate `expression` to `value`, or
        NotImplemented for operators the ORM can derive (e.g. 'not in'). """
        if operator in ('>', '>=', '<', '<='):
            return SQL("%s %s %s", expression, SQL(operator), value)
        if operator == 'in':
            values = [v for v in value if v is not None and v is not False]
            conditions = []
            if values:
                conditions.append(SQL("%s IN %s", expression, tuple(values)))
            if len(values) != len(value):
                conditions.append(SQL("%s IS NULL", expression))
            if not conditions:
                return SQL("FALSE")
            return SQL("(%s)", SQL(" OR ").join(conditions))
        return NotImplemented

    def _followup_amount_search(self, operator, value, overdue_only):
        if operator == 'in':
            # partners without receivable lines have a zero balance
            value = [v or 0.0 for v in value]
        having = self._followup_having_condition(SQL("SUM(bal2)"), operator, value)
        if having is NotImplemented:
            return NotImplemented
        query = SQL("""
            SELECT pid AS partner_id, SUM(bal2) FROM (
                SELECT
                    CASE WHEN bal IS NOT NULL THEN bal ELSE 0.0 END AS bal2,
                    p.id as pid
                FROM (
                    SELECT
                        (l.debit - l.credit) AS bal,
                        l.partner_id
                    FROM account_move_line l
                    LEFT JOIN account_account a ON a.id = l.account_id
                    JOIN account_move m ON m.id = l.move_id
                    WHERE a.account_type = 'asset_receivable'
                    %s AND l.full_reconcile_id IS NULL
                    AND l.parent_state = 'posted'
                    AND NOT COALESCE(m.followup_disputed, FALSE)
                    AND l.company_id = %s
                ) AS l
                RIGHT JOIN res_partner p ON p.id = partner_id
            ) AS pl
            GROUP BY pid HAVING %s
        """,
            (SQL("AND COALESCE(l.date_maturity, l.date) <= %s", fields.Date.context_today(self))
             if overdue_only else SQL()),
            self.env.company.id,
            having,
        )
        self.env.flush_all()
        self.env.cr.execute(query)
        return [('id', 'in', [x[0] for x in self.env.cr.fetchall()])]

    def _payment_overdue_search(self, operator, operand):
        return self._followup_amount_search(operator, operand, overdue_only=True)

    def _payment_earliest_date_search(self, operator, operand):
        having = self._followup_having_condition(
            SQL("MIN(COALESCE(l.date_maturity, l.date))"), operator, operand)
        if having is NotImplemented:
            return NotImplemented
        self.env.flush_all()
        self.env.cr.execute(SQL("""
            SELECT l.partner_id, %s FROM account_move_line l
            LEFT JOIN account_account a ON a.id = l.account_id
            JOIN account_move m ON m.id = l.move_id
            WHERE a.account_type = 'asset_receivable'
            AND l.company_id = %s
            AND l.full_reconcile_id IS NULL
            AND l.parent_state = 'posted'
            AND NOT COALESCE(m.followup_disputed, FALSE)
            AND l.partner_id IS NOT NULL
            GROUP BY l.partner_id
        """, having, self.env.company.id))
        rows = self.env.cr.fetchall()
        domain = [('id', 'in', [partner_id for partner_id, matches in rows if matches])]
        if operator == 'in' and any(v is None or v is False for v in operand):
            # partners without open receivable lines have no due date either
            domain = ['|', ('id', 'not in', [partner_id for partner_id, __ in rows])] + domain
        return domain

    def _payment_due_search(self, operator, operand):
        return self._followup_amount_search(operator, operand, overdue_only=False)

    # -------------------------------------------------------------------------
    # Open items
    # -------------------------------------------------------------------------

    def _followup_statement_lines(self, date=None, overdue_only=False):
        """ The open items of the customer in the current company, as printed and emailed.

        :return: list of {'currency', 'lines': [...], 'total', 'total_overdue'}
        """
        self.ensure_one()
        date = date or fields.Date.context_today(self)
        company = self.env.company
        partner = self.commercial_partner_id
        domain = [
            ('partner_id', '=', partner.id),
            ('company_id', '=', company.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '!=', 0),
        ]
        lines = self.env['account.move.line'].sudo().search(domain, order='date_maturity, date, id')
        by_currency = defaultdict(list)
        for line in lines:
            overdue = line._followup_due_date() <= date
            if overdue_only and not overdue:
                continue
            foreign = line.currency_id and line.currency_id != company.currency_id
            currency = line.currency_id if foreign else company.currency_id
            move = line.move_id
            by_currency[currency].append({
                'line': line,
                'move': move,
                'name': move.name,
                'ref': move.ref or (line.name if line.name != move.name else ''),
                'date': line.date,
                'date_maturity': line._followup_due_date(),
                'days_overdue': max(line._followup_age(date), 0),
                'amount': line.amount_currency if foreign else line.balance,
                'residual': line.amount_residual_currency if foreign else line.amount_residual,
                'overdue': overdue,
                'disputed': move.followup_disputed,
                'portal_url': move.get_portal_url() if move.is_invoice(include_receipts=True) else False,
            })
        result = []
        for currency, items in by_currency.items():
            result.append({
                'currency': currency,
                'lines': items,
                'total': sum(item['residual'] for item in items),
                'total_overdue': sum(item['residual'] for item in items
                                     if item['overdue'] and not item['disputed']),
                'ageing': self._followup_ageing(items),
            })
        return result

    @api.model
    def _followup_ageing(self, items):
        """ :return: [(label, amount)] of the open items by age, the disputed ones left out """
        ageing = []
        for _key, label, low, high in AGEING_BUCKETS:
            amount = sum(
                item['residual'] for item in items
                if not item['disputed'] and item['days_overdue'] >= low
                and (high is None or item['days_overdue'] <= high))
            ageing.append((label, amount))
        return ageing

    def get_followup_table_html(self):
        """ The overdue items of the customer, inserted in the reminder emails """
        self.ensure_one()
        partner = self.commercial_partner_id
        followup_table = Markup()
        today = fields.Date.context_today(self)
        for currency_dict in partner._followup_statement_lines(today):
            currency = currency_dict['currency']
            rows = Markup()
            for item in currency_dict['lines']:
                if item['disputed']:
                    continue
                cell = Markup('<td style="padding: 4px 8px; border-bottom: 1px solid #eee;">%s</td>')
                amount_cell = Markup(
                    '<td style="padding: 4px 8px; border-bottom: 1px solid #eee; text-align: right;">%s</td>')
                if item['overdue'] and item['residual'] > 0:
                    cell = Markup('<td style="padding: 4px 8px; border-bottom: 1px solid #eee;"><b>%s</b></td>')
                    amount_cell = Markup('<td style="padding: 4px 8px; border-bottom: 1px solid #eee; '
                                         'text-align: right;"><b>%s</b></td>')
                reference = item['name']
                if item['portal_url']:
                    reference = Markup('<a href="%s">%s</a>') % (
                        partner.get_base_url() + item['portal_url'], item['name'])
                rows += Markup('<tr>%s%s%s%s%s</tr>') % (
                    cell % format_date(self.env, item['date']),
                    cell % reference,
                    cell % (item['ref'] or ''),
                    cell % format_date(self.env, item['date_maturity']),
                    amount_cell % formatLang(self.env, item['residual'], digits=currency.decimal_places),
                )
            if not rows:
                continue
            header = Markup('<th style="padding: 4px 8px; text-align: left; border-bottom: 2px solid #ccc;">%s</th>')
            followup_table += Markup(
                '<table border="0" cellpadding="0" cellspacing="0" width="100%%" style="border-collapse: collapse;">'
                '<tr>%s%s%s%s<th style="padding: 4px 8px; text-align: right; border-bottom: 2px solid #ccc;">'
                '%s (%s)</th></tr>%s</table>'
                '<p style="text-align: right;"><b>%s: %s</b></p>') % (
                header % _("Invoice Date"), header % _("Invoice"), header % _("Reference"),
                header % _("Due Date"), _("Amount Due"), currency.symbol, rows,
                _("Overdue"), formatLang(self.env, currency_dict['total_overdue'], currency_obj=currency))
        return followup_table

    # -------------------------------------------------------------------------
    # Reminders
    # -------------------------------------------------------------------------

    def _followup_level_text(self, date=None):
        """ The message of the level reached by the customer, printed at the top of the statement """
        self.ensure_one()
        level = self.latest_followup_level_id or self.followup_level_due_id
        if not level or not level.description:
            return ''
        date = date or fields.Date.context_today(self)
        return level.with_context(lang=self.lang).description % {
            'partner_name': self.name,
            'date': format_date(self.env, date, lang_code=self.lang),
            'company_name': self.env.company.name,
            'user_signature': self.env.user.name,
        }

    def _followup_email_recipients(self):
        """ The invoicing contacts of the customer, or the customer itself """
        self.ensure_one()
        partner = self.commercial_partner_id
        recipients = partner.child_ids.filtered(lambda child: child.type == 'invoice' and child.email)
        if not recipients and partner.email:
            recipients = partner
        return recipients

    def _followup_overdue_invoices(self):
        self.ensure_one()
        items = self._followup_statement_lines(overdue_only=True)
        return self.env['account.move'].union(*[
            item['move'] for currency in items for item in currency['lines']
            if not item['disputed'] and item['residual'] > 0 and item['move'].is_invoice(include_receipts=True)
        ])

    def _followup_invoice_attachments(self):
        """ The PDF of the overdue invoices, attached to the reminder """
        self.ensure_one()
        attachments = self.env['ir.attachment']
        for invoice in self._followup_overdue_invoices():
            content, _report_type = self.env['ir.actions.report']._render_qweb_pdf(
                'account.account_invoices', invoice.ids)
            attachments |= self.env['ir.attachment'].create({
                'name': '%s.pdf' % (invoice.name or _('Invoice')).replace('/', '_'),
                'raw': content,
                'mimetype': 'application/pdf',
                'res_model': 'res.partner',
                'res_id': self.id,
            })
        return attachments

    def _followup_send_email(self, template=None, subject=None, body=None, recipients=None,
                             attach_invoices=False):
        """ Send a reminder email to the customer and keep it in the chatter.

        :return: whether the email could be sent, i.e. the customer has an email address
        """
        self.ensure_one()
        recipients = recipients if recipients is not None else self._followup_email_recipients()
        if not recipients:
            return False
        template = template or self.env.ref(
            'om_account_followup.email_template_om_account_followup_default', raise_if_not_found=False)
        if body is None or subject is None:
            if not template:
                raise UserError(_('Choose the email template of the reminder.'))
            rendered = template.with_context(followup=True)._generate_template(self.ids, ('subject', 'body_html'))
            subject = subject if subject is not None else rendered[self.id].get('subject')
            body = body if body is not None else rendered[self.id].get('body_html')
        # a rendered template, or the body edited in the reminder dialog
        body = body if isinstance(body, Markup) else Markup(body or '')
        attachments = self._followup_invoice_attachments() if attach_invoices else self.env['ir.attachment']
        self.with_context(mail_post_autofollow=False).message_post(
            body=body,
            subject=subject,
            partner_ids=recipients.ids,
            attachment_ids=attachments.ids,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            email_layout_xmlid='mail.mail_notification_light',
        )
        return True

    def _followup_schedule_action(self, level):
        """ The manual action of a level becomes an activity of the responsible """
        self.ensure_one()
        user = self.payment_responsible_id or level.manual_action_responsible_id or self.env.user
        activity_type = self.env.ref('om_account_followup.mail_activity_type_followup')
        existing = self.activity_ids.filtered(lambda activity: activity.activity_type_id == activity_type)
        note = level.manual_action_note or level.name
        if existing:
            existing[:1].write({
                'summary': level.name,
                'note': Markup('%s<br/>%s') % (existing[:1].note or '', note),
                'user_id': user.id,
            })
            return existing[:1]
        return self.activity_schedule(
            'om_account_followup.mail_activity_type_followup',
            date_deadline=fields.Date.context_today(self),
            summary=level.name,
            note=note,
            user_id=user.id,
        )

    def _followup_process(self, date=None, send_email=None, print_letter=None, template=None, subject=None,
                          body=None, recipients=None, attach_invoices=False, levels=None):
        """ Send the reminders due to the customers: move their open items to the level reached, send the
        email, schedule the manual action and tell which letters to print.

        :param send_email, print_letter: None to follow the level
        :param levels: {partner: level} to force the level of the reminder
        :return: {'emails': int, 'unknown_emails': partners, 'letters': partners, 'actions': partners}
        """
        date = date or fields.Date.context_today(self)
        state = self._followup_state(date)
        result = {'emails': 0, 'unknown_emails': self.browse(), 'letters': self.browse(),
                  'actions': self.browse()}
        for partner in self:
            values = state[partner]
            level = (levels or {}).get(partner) or values['level_due'] or partner.latest_followup_level_id
            for line, line_level in values['lines_due'].items():
                line.sudo().write({'followup_line_id': line_level.id, 'followup_date': date})
            if not level:
                if send_email:
                    if partner._followup_send_email(template, subject, body, recipients, attach_invoices):
                        result['emails'] += 1
                    else:
                        result['unknown_emails'] |= partner
                if print_letter:
                    result['letters'] |= partner
                continue
            if send_email if send_email is not None else level.send_email:
                if partner._followup_send_email(template or level.email_template_id, subject, body, recipients,
                                                attach_invoices):
                    result['emails'] += 1
                else:
                    result['unknown_emails'] |= partner
                    partner.activity_schedule(
                        'om_account_followup.mail_activity_type_followup',
                        date_deadline=date,
                        summary=_('Reminder not sent'),
                        note=_('The reminder could not be emailed: the customer has no email address.'),
                        user_id=(partner.payment_responsible_id or self.env.user).id,
                    )
            if print_letter if print_letter is not None else level.send_letter:
                result['letters'] |= partner
            if level.manual_action and not self.env.context.get('followup_skip_actions'):
                partner._followup_schedule_action(level)
                result['actions'] |= partner
            partner.message_post(body=_('Follow-up reminder sent: %s', level.name))
        return result

    # -------------------------------------------------------------------------
    # Legacy entry points, used by the batch processing
    # -------------------------------------------------------------------------

    def do_partner_manual_action(self, partner_ids):
        for partner in self.browse(partner_ids):
            level = partner.latest_followup_level_id
            if level:
                partner._followup_schedule_action(level)

    def do_partner_print(self, wizard_partner_ids, data):
        """ :param wizard_partner_ids: ids of follow-up statistics by partner """
        if not wizard_partner_ids:
            return {}
        partners = self.env['followup.stat.by.partner'].browse(wizard_partner_ids).partner_id
        return partners._followup_statement_action()

    def do_partner_mail(self):
        unknown_mails = 0
        for partner in self:
            level = partner.latest_followup_level_id
            template = level.email_template_id if level and level.send_email else None
            if not partner._followup_send_email(template):
                unknown_mails += 1
                partner.activity_schedule(
                    'om_account_followup.mail_activity_type_followup',
                    date_deadline=fields.Date.context_today(self),
                    summary=_('Reminder not sent'),
                    note=_('The reminder could not be emailed: the customer has no email address.'),
                    user_id=(partner.payment_responsible_id or self.env.user).id,
                )
        return unknown_mails

    def write(self, vals):
        if vals.get("payment_responsible_id", False):
            for part in self:
                if part.payment_responsible_id != \
                        self.env['res.users'].browse(vals["payment_responsible_id"]):
                    # Find partner_id of user put as responsible
                    responsible_partner_id = self.env["res.users"].browse(
                        vals['payment_responsible_id']).partner_id.id
                    part.message_post(
                        body=Markup("%s <b>%s</b>") % (
                            _("You became responsible to do the next action "
                              "for the payment follow-up of"),
                            part._get_html_link()),
                        message_type='comment',
                        partner_ids=[responsible_partner_id])
        return super().write(vals)

    def action_done(self):
        return self.write({'payment_next_action_date': False,
                           'payment_next_action': '',
                           'payment_responsible_id': False})

    def do_button_print(self):
        self.ensure_one()
        return self.action_followup_print_statement()

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def _followup_statement_action(self):
        return self.env.ref('om_account_followup.action_report_customer_statement').report_action(self)

    def action_followup_print_statement(self):
        partners = self.commercial_partner_id
        company = self.env.company
        if not self.env['account.move.line'].search_count([
            ('partner_id', 'in', partners.ids),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('company_id', '=', company.id),
        ], limit=1):
            raise UserError(_("There is nothing open to print in the statement of the current company."))
        for partner in partners:
            partner.message_post(body=_('Customer statement printed'))
        return partners._followup_statement_action()

    def action_followup_send(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Reminder'),
            'res_model': 'followup.send',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_ids': self.commercial_partner_id.ids},
        }

    def action_followup_log_call(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Log a Call'),
            'res_model': 'mail.activity',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_res_model_id': self.env['ir.model']._get_id('res.partner'),
                'default_res_id': self.id,
                'default_activity_type_id': self.env.ref('mail.mail_activity_data_call').id,
                'default_summary': _('Payment follow-up call'),
                'default_user_id': (self.payment_responsible_id or self.env.user).id,
            },
        }

    def action_followup_exclude(self):
        self.write({'followup_excluded': True})

    def action_followup_include(self):
        self.write({'followup_excluded': False, 'followup_exclusion_reason': False})

    def action_followup_clear_promise(self):
        self.write({'followup_promise_date': False, 'followup_promise_amount': 0.0})

    def action_followup_open_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Open Items'),
            'res_model': 'account.move.line',
            'view_mode': 'list',
            'views': [(self.env.ref('om_account_followup.view_followup_open_items').id, 'list')],
            'domain': [('partner_id', '=', self.commercial_partner_id.id),
                       ('company_id', '=', self.env.company.id),
                       ('account_id.account_type', '=', 'asset_receivable'),
                       ('parent_state', '=', 'posted'),
                       ('reconciled', '=', False)],
            'context': {'create': False},
        }
