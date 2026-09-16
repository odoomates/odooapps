from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import SQL
from odoo.tools.misc import formatLang


class ResPartner(models.Model):
    _inherit = "res.partner"

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

    def do_partner_manual_action(self, partner_ids):
        for partner in self.browse(partner_ids):
            followup_level = partner.latest_followup_level_id
            if partner.payment_next_action:
                action_text = \
                    (partner.payment_next_action or '') + "\n" + \
                    (followup_level.manual_action_note or '')
            else:
                action_text = followup_level.manual_action_note or ''

            action_date = partner.payment_next_action_date or \
                fields.Date.context_today(self)

            if partner.payment_responsible_id:
                responsible_id = partner.payment_responsible_id.id
            else:
                p = followup_level.manual_action_responsible_id
                responsible_id = p and p.id or False
            partner.write({'payment_next_action_date': action_date,
                           'payment_next_action': action_text,
                           'payment_responsible_id': responsible_id})

    def do_partner_print(self, wizard_partner_ids, data):
        if not wizard_partner_ids:
            return {}
        data['partner_ids'] = wizard_partner_ids
        datas = {
            'ids': wizard_partner_ids,
            'model': 'followup.followup',
            'form': data
        }
        return self.env.ref(
            'om_account_followup.action_report_followup').report_action(
            self, data=datas)

    def do_partner_mail(self):
        ctx = self.env.context.copy()
        ctx['followup'] = True
        template = 'om_account_followup.email_template_om_account_followup_default'
        unknown_mails = 0
        for partner in self:
            partners_to_email = [child for child in partner.child_ids if
                                 child.type == 'invoice' and child.email]
            if not partners_to_email and partner.email:
                partners_to_email = [partner]
            if partners_to_email:
                level = partner.latest_followup_level_id
                for partner_to_email in partners_to_email:
                    if level and level.send_email and \
                            level.email_template_id and \
                            level.email_template_id.id:
                        level.email_template_id.with_context(ctx).send_mail(
                            partner_to_email.id)
                    else:
                        mail_template_id = self.env.ref(template)
                        mail_template_id.with_context(ctx).send_mail(
                            partner_to_email.id)
                if partner not in partners_to_email:
                    partner.message_post(body=_(
                        'Overdue email sent to %s', ', '.join(
                            ['%s <%s>' % (partner.name, partner.email) for
                             partner in partners_to_email])))
            else:
                unknown_mails = unknown_mails + 1
                action_text = _("Email not sent because of email address "
                                "of partner not filled in")
                if partner.payment_next_action_date:
                    payment_action_date = min(
                        fields.Date.context_today(self),
                        partner.payment_next_action_date)
                else:
                    payment_action_date = fields.Date.context_today(self)
                if partner.payment_next_action:
                    payment_next_action = \
                        partner.payment_next_action + " \n " + action_text
                else:
                    payment_next_action = action_text
                partner.with_context(ctx).write(
                    {'payment_next_action_date': payment_action_date,
                     'payment_next_action': payment_next_action})
        return unknown_mails

    def get_followup_table_html(self):
        self.ensure_one()
        partner = self.commercial_partner_id
        followup_table = Markup()
        if partner.unreconciled_aml_ids:
            company = self.env.company
            current_date = fields.Date.context_today(self)
            report = self.env['report.om_account_followup.report_followup']
            final_res = report._lines_get_with_partner(partner, company.id)

            for currency_dict in final_res:
                currency = currency_dict['currency']
                followup_table += Markup('''
                <table border="2" width="100%%">
                <tr>
                    <td>%s</td>
                    <td>%s</td>
                    <td>%s</td>
                    <td>%s</td>
                    <td>%s (%s)</td>
                </tr>
                ''') % (_("Invoice Date"), _("Description"), _("Reference"),
                        _("Due Date"), _("Amount"), currency.symbol)
                total = 0
                for aml in currency_dict['line']:
                    total += aml['balance']
                    cell = Markup("<td>%s</td>")
                    if aml['due_date'] <= current_date and aml['balance'] > 0:
                        cell = Markup("<td><b>%s</b></td>")
                    amount = formatLang(self.env, aml['balance'], digits=currency.decimal_places)
                    followup_table += Markup("<tr>%s</tr>") % Markup().join(
                        cell % value for value in (
                            aml['date'], aml['name'], aml['ref'] or '',
                            aml['date_maturity'] or aml['date'], amount))

                total = formatLang(self.env, total, currency_obj=currency)
                followup_table += Markup('''<tr> </tr>
                                </table>
                                <center>%s : %s </center>''') % (_("Amount due"), total)
        return followup_table

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
        company_id = self.env.company.id
        if not self.env['account.move.line'].search(
                [('partner_id', '=', self.id),
                 ('account_id.account_type', '=', 'asset_receivable'),
                 ('full_reconcile_id', '=', False),
                 ('company_id', '=', company_id),
                 '|', ('date_maturity', '=', False),
                 ('date_maturity', '<=', fields.Date.context_today(self))]):
            raise ValidationError(
                _("The partner does not have any accounting entries to "
                  "print in the overdue report for the current company."))
        self.message_post(body=_('Printed overdue payments report'))

        wizard_partner_ids = [self.env['followup.stat.by.partner']._get_stat_id(self.id, company_id)]
        followup_ids = self.env['followup.followup'].search(
            [('company_id', '=', company_id)])
        if not followup_ids:
            raise ValidationError(_(
                "There is no followup plan defined for the current company."))
        data = {
            'date': fields.Date.context_today(self),
            'followup_id': followup_ids[0].id,
        }
        return self.do_partner_print(wizard_partner_ids, data)

    @api.depends_context('company')
    def _get_amounts_and_date(self):
        company = self.env.company
        current_date = fields.Date.context_today(self)
        for partner in self:
            worst_due_date = False
            amount_due = amount_overdue = 0.0
            for aml in partner.unreconciled_aml_ids:
                if (aml.company_id == company):
                    date_maturity = aml.date_maturity or aml.date
                    if not worst_due_date or date_maturity < worst_due_date:
                        worst_due_date = date_maturity
                    amount_due += aml.result
                    if (date_maturity <= current_date):
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
                        (debit - credit) AS bal,
                        partner_id
                    FROM account_move_line l
                    LEFT JOIN account_account a ON a.id = l.account_id
                    WHERE a.account_type = 'asset_receivable'
                    %s AND full_reconcile_id IS NULL
                    AND l.company_id = %s
                ) AS l
                RIGHT JOIN res_partner p ON p.id = partner_id
            ) AS pl
            GROUP BY pid HAVING %s
        """,
            SQL("AND COALESCE(l.date_maturity, l.date) <= %s", fields.Date.context_today(self)) if overdue_only else SQL(),
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
            SELECT partner_id, %s FROM account_move_line l
            LEFT JOIN account_account a ON a.id = l.account_id
            WHERE a.account_type = 'asset_receivable'
            AND l.company_id = %s
            AND l.full_reconcile_id IS NULL
            AND partner_id IS NOT NULL
            GROUP BY partner_id
        """, having, self.env.company.id))
        rows = self.env.cr.fetchall()
        domain = [('id', 'in', [partner_id for partner_id, matches in rows if matches])]
        if operator == 'in' and any(v is None or v is False for v in operand):
            # partners without open receivable lines have no due date either
            domain = ['|', ('id', 'not in', [partner_id for partner_id, __ in rows])] + domain
        return domain

    def _payment_due_search(self, operator, operand):
        return self._followup_amount_search(operator, operand, overdue_only=False)

    payment_responsible_id = fields.Many2one(
        'res.users', ondelete='set null',
        string='Follow-up Responsible', tracking=True, copy=False,
        help="Optionally you can assign a user to this field, which will make "
             "him responsible for the action.")
    payment_note = fields.Text(
        'Customer Payment Promise', help="Payment Note", copy=False
    )
    payment_next_action = fields.Text(
        'Next Action', copy=False, tracking=True,
        help="This is the next action to be taken.  It will automatically be "
             "set when the partner gets a follow-up level that requires a manual action. "
    )
    payment_next_action_date = fields.Date(
        'Next Action Date', copy=False,
        help="This is when the manual follow-up is needed. The date will be "
             "set to the current date when the partner gets a follow-up level "
             "that requires a manual action. Can be practical to set manually "
             "e.g. to see if he keeps his promises."
    )
    unreconciled_aml_ids = fields.One2many(
        'account.move.line', 'partner_id',
        domain=[('full_reconcile_id', '=', False), ('account_id.account_type', '=', 'asset_receivable')]
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
