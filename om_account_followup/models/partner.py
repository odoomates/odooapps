from functools import reduce
from markupsafe import Markup, escape
from lxml import etree
from odoo import api, fields, models, _
from datetime import datetime
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL
from odoo.tools.misc import formatLang


class ResPartner(models.Model):
    _inherit = "res.partner"

    def fields_view_get(self, view_id=None, view_type='form', toolbar=False,
                        submenu=False):
        res = super(ResPartner, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar,
            submenu=submenu)
        if view_type == 'form' and self.env.context.get('Followupfirst'):
            doc = etree.XML(res['arch'], parser=None, base_url=None)
            first_node = doc.xpath("//page[@name='followup_tab']")
            root = first_node[0].getparent()
            root.insert(0, first_node[0])
            res['arch'] = etree.tostring(doc, encoding="utf-8")
        return res

    @api.depends_context('company')
    def _get_latest(self):
        company = self.env.company
        for partner in self:
            amls = partner.unreconciled_aml_ids
            latest_date = False
            latest_level = False
            latest_days = False
            latest_level_without_lit = False
            latest_days_without_lit = False
            for aml in amls:
                aml_followup = aml.followup_line_id
                if (aml.company_id == company) and aml_followup and \
                        (not latest_days or latest_days < aml_followup.delay):
                    latest_days = aml_followup.delay
                    latest_level = aml_followup.id
                if (aml.company_id == company) and aml.followup_date and (
                        not latest_date or latest_date < aml.followup_date):
                    latest_date = aml.followup_date
                if (aml.company_id == company) and \
                        (aml_followup and (not latest_days_without_lit or
                         latest_days_without_lit < aml_followup.delay)):
                    latest_days_without_lit = aml_followup.delay
                    latest_level_without_lit = aml_followup.id
            partner.latest_followup_date = latest_date
            partner.latest_followup_level_id = latest_level
            partner.latest_followup_level_id_without_lit = latest_level_without_lit

    def do_partner_manual_action_dermanord(self, followup_line):
        action_text = followup_line.manual_action_note or ''

        action_date = self.payment_next_action_date or \
            fields.Date.today()
        if self.payment_responsible_id:
            responsible_id = self.payment_responsible_id.id
        else:
            p = followup_line.manual_action_responsible_id
            responsible_id = p and p.id or False
        self.write({'payment_next_action_date': action_date,
                    'payment_next_action': action_text,
                    'payment_responsible_id': responsible_id})

    def do_partner_manual_action(self, partner_ids):
        for partner in self.browse(partner_ids):
            followup_without_lit = partner.latest_followup_level_id_without_lit
            if partner.payment_next_action:
                action_text = \
                    (partner.payment_next_action or '') + "\n" + \
                    (followup_without_lit.manual_action_note or '')
            else:
                action_text = followup_without_lit.manual_action_note or ''

            action_date = partner.payment_next_action_date or \
                fields.Date.today()

            if partner.payment_responsible_id:
                responsible_id = partner.payment_responsible_id.id
            else:
                p = followup_without_lit.manual_action_responsible_id
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
                level = partner.latest_followup_level_id_without_lit
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
                        'Overdue email sent to %s' % ', '.join(
                            ['%s <%s>' % (partner.name, partner.email) for
                             partner in partners_to_email])))
            else:
                unknown_mails = unknown_mails + 1
                action_text = _("Email not sent because of email address "
                                "of partner not filled in")
                if partner.payment_next_action_date:
                    payment_action_date = min(
                        fields.Date.today(),
                        partner.payment_next_action_date)
                else:
                    payment_action_date = fields.Date.today()
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
        followup_table = ''
        if partner.unreconciled_aml_ids:
            company = self.env.company
            current_date = fields.Date.today()
            report = self.env['report.om_account_followup.report_followup']
            final_res = report._lines_get_with_partner(partner, company.id)

            for currency_dict in final_res:
                currency = currency_dict.get('line', [
                    {'currency_id': company.currency_id}])[0]['currency_id']
                followup_table += '''
                <table border="2" width=100%%>
                <tr>
                    <td>''' + _("Invoice Date") + '''</td>
                    <td>''' + _("Description") + '''</td>
                    <td>''' + _("Reference") + '''</td>
                    <td>''' + _("Due Date") + '''</td>
                    <td>''' + _("Amount") + " (%s)" % (
                    currency.symbol) + '''</td>
                    <td>''' + _("Lit.") + '''</td>
                </tr>
                '''
                total = 0
                for aml in currency_dict['line']:
                    total += aml['balance']
                    strbegin = "<TD>"
                    strend = "</TD>"
                    date = aml['date_maturity'] or aml['date']
                    # date = datetime.strptime(date, "%d/%m/%Y").date()
                    if date <= current_date and aml['balance'] > 0:
                        strbegin = "<TD><B>"
                        strend = "</B></TD>"
                    followup_table += "<TR>" + strbegin + str(aml['date']) + \
                                      strend + strbegin + aml['name'] + \
                                      strend + strbegin + \
                                      (aml['ref'] or '') + strend + \
                                      strbegin + str(date) + strend + \
                                      strbegin + str(aml['balance']) + \
                                      strend + "</TR>"

                total = reduce(lambda x, y: x + y['balance'],
                               currency_dict['line'], 0.00)
                total = formatLang(self.env, total, currency_obj=currency)
                followup_table += '''<tr> </tr>
                                </table>
                                <center>''' + _(
                    "Amount due") + ''' : %s </center>''' % (total)
        return followup_table

    def write(self, vals):
        if vals.get("payment_responsible_id", False):
            for part in self:
                if part.payment_responsible_id != \
                        self.env['res.users'].browse(vals["payment_responsible_id"]):
                    # Find partner_id of user put as responsible
                    responsible_partner_id = self.env["res.users"].browse(
                        vals['payment_responsible_id']).partner_id.id
                    body_html = Markup(_(
                        "You became responsible to do the next action for the payment follow-up of "
                        "<b><a href='#id={id}&view_type=form&model=res.partner'>{name}</a></b>"
                    )).format(
                        id=part.id,
                        name=escape(part.name)
                    )
                    part.message_post(
                        body=body_html,
                        message_type='comment',
                        partner_ids=[responsible_partner_id])
        return super(ResPartner, self).write(vals)

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
                 ('parent_state', '=', 'posted'),
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
            'date': fields.Date.today(),
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

    def _followup_search(self, operator, operand, search):
        """ Odoo 18 gives the search methods the operator as written: bring '=', '!='
        and 'not in' down to 'in' and negate the result, as the ORM of 19 does. """
        negate = operator in ('!=', 'not in')
        if operator in ('=', '!='):
            operand = [operand]
        if operator in ('=', '!=', 'not in'):
            operator = 'in'
        domain = search(operator, operand)
        if domain is NotImplemented:
            raise UserError(_('Operator %s is not supported for this search.', operator))
        return ['!', *domain] if negate else domain

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
                    WHERE a.account_type = 'asset_receivable'
                    %s AND l.full_reconcile_id IS NULL
                    AND l.parent_state = 'posted'
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
        return self._followup_search(
            operator, operand, lambda op, value: self._followup_amount_search(op, value, overdue_only=True))

    def _payment_earliest_date_search(self, operator, operand):
        return self._followup_search(operator, operand, self._followup_earliest_date_search)

    def _followup_earliest_date_search(self, operator, operand):
        having = self._followup_having_condition(
            SQL("MIN(COALESCE(l.date_maturity, l.date))"), operator, operand)
        if having is NotImplemented:
            return NotImplemented
        self.env.flush_all()
        self.env.cr.execute(SQL("""
            SELECT l.partner_id, %s FROM account_move_line l
            LEFT JOIN account_account a ON a.id = l.account_id
            WHERE a.account_type = 'asset_receivable'
            AND l.company_id = %s
            AND l.full_reconcile_id IS NULL
            AND l.parent_state = 'posted'
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
        return self._followup_search(
            operator, operand, lambda op, value: self._followup_amount_search(op, value, overdue_only=False))

    def _get_partners(self):
        partners = set()
        for aml in self:
            if aml.partner_id:
                partners.add(aml.partner_id.id)
        return list(partners)

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

    latest_followup_sequence = fields.Integer(
        'Sequence',
        help="Gives the sequence order when displaying a list of follow-up lines.", default=0
    )
    latest_followup_level_id_without_lit = fields.Many2one(
        'followup.line', compute='_get_latest', compute_sudo=True,
        string="Latest Follow-up Level without litigation",
        help="The maximum follow-up level without taking into "
             "account the account move lines with litigation")
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
