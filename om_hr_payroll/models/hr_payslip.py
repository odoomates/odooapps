from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .hr_rule_parameter import RuleParameters
from .hr_salary_bracket import SalaryBrackets
import babel
from datetime import date, datetime, time
from dateutil.relativedelta import relativedelta
from pytz import timezone


# the worked days line holding the time the employee was due to work, the others being the time off
WORKED_DAYS_CODE = 'WORK100'


class YearToDate:
    """ What the employee has already been paid since the beginning of the year, by salary rule.

    The rules read it as ``ytd.GROSS``. It holds the payslips already confirmed, not the one being computed:
    a rule needing the year including this period writes ``ytd.GROSS + categories.GROSS``, which says what it
    does and does not depend on the order the rules are computed in.
    """

    def __init__(self, env, employee_id, date_from, date_to):
        self.env = env
        self.employee_id = employee_id
        self.date_from = date_from
        self.date_to = date_to
        self.totals = {}

    def __getattr__(self, code):
        return self.total(code)

    def total(self, code):
        """ :return: the total of the rule `code` over the payslips of the year already confirmed """
        if code not in self.totals:
            self.env.flush_all()
            self.env.cr.execute("""
                SELECT COALESCE(SUM(CASE WHEN slip.credit_note THEN -line.total ELSE line.total END), 0.0)
                  FROM hr_payslip slip
                  JOIN hr_payslip_line line ON line.slip_id = slip.id
                 WHERE slip.employee_id = %s
                   AND slip.state = 'done'
                   AND slip.date_from >= %s
                   AND slip.date_to <= %s
                   AND line.code = %s
            """, (self.employee_id, self.date_from, self.date_to, code))
            self.totals[code] = self.env.cr.fetchone()[0] or 0.0
        return self.totals[code]

# what may still be written on a confirmed payslip: the trail of what happened to it
PAYSLIP_CLOSED_WRITABLE = {
    'state', 'paid', 'note', 'move_id', 'date', 'number', 'message_ids', 'message_follower_ids',
    'activity_ids', 'line_ids', 'payslip_run_id',
}


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _description = 'Pay Slip'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    struct_id = fields.Many2one('hr.payroll.structure', string='Structure',
                                help='Defines the rules that have to be applied to this payslip, accordingly '
                                     'to the version/contract chosen.', tracking=True)
    name = fields.Char(string='Payslip Name')
    number = fields.Char(string='Reference', copy=False, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, tracking=True)
    date_from = fields.Date(string='Date From', required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1), tracking=True)
    date_to = fields.Date(string='Date To', required=True,
                          default=lambda self: fields.Date.context_today(self) + relativedelta(day=31), tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Rejected'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft',
        help="""* When the payslip is created the status is \'Draft\'
                \n* If the payslip is under verification, the status is \'Waiting\'.
                \n* If the payslip is confirmed then status is set to \'Done\'.
                \n* When user cancel payslip the status is \'Rejected\'.""", tracking=True)

    line_ids = fields.One2many('hr.payslip.line', 'slip_id', string='Payslip Lines')
    company_id = fields.Many2one(
        'res.company', string='Company', copy=False,
        default=lambda self: self.env.company
    )
    worked_days_line_ids = fields.One2many(
        'hr.payslip.worked_days', 'payslip_id',
        string='Payslip Worked Days', copy=True
    )
    input_line_ids = fields.One2many(
        'hr.payslip.input', 'payslip_id',
        string='Payslip Inputs', copy=True
    )
    paid = fields.Boolean(string='Made Payment Order ? ', copy=False, tracking=True)
    note = fields.Text(string='Internal Note')

    version_id = fields.Many2one('hr.version', string='Employment Version/Contract', tracking=True)

    details_by_salary_rule_category = fields.One2many('hr.payslip.line',
                                                      compute='_compute_details_by_salary_rule_category',
                                                      string='Details by Salary Rule Category')
    credit_note = fields.Boolean(string='Credit Note',
                                 help="Indicates this payslip has a refund of another", tracking=True)
    payslip_run_id = fields.Many2one('hr.payslip.run', string='Payslip Batches', copy=False, tracking=True)
    payslip_count = fields.Integer(compute='_compute_payslip_count', string="Payslip Computation Details")

    def _compute_details_by_salary_rule_category(self):
        for payslip in self:
            payslip.details_by_salary_rule_category = payslip.mapped('line_ids').filtered(lambda line: line.category_id)

    def _compute_payslip_count(self):
        for payslip in self:
            payslip.payslip_count = len(payslip.line_ids)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        if any(self.filtered(lambda payslip: payslip.date_from > payslip.date_to)):
            raise ValidationError(_("Payslip 'Date From' must be earlier 'Date To'."))

    def _is_payroll_manager(self):
        return self.env.su or self.env.user.has_group('om_hr_payroll.group_hr_payroll_manager')

    def _check_own_payslip(self):
        """ Payroll officers do not confirm, cancel or reset their own payslips: a payroll manager does. """
        if self.env.su or self.env.user.has_group('om_hr_payroll.group_hr_payroll_manager'):
            return
        own = self.filtered(lambda payslip: payslip.employee_id.user_id == self.env.user)
        if own:
            raise UserError(_('You cannot change the status of your own payslip %s: ask a payroll manager.',
                              ', '.join(own.mapped(lambda payslip: payslip.number or payslip.name or ''))))

    def action_payslip_draft(self):
        self._check_own_payslip()
        confirmed = self.filtered(lambda payslip: payslip.state == 'done')
        if confirmed and not self._is_payroll_manager():
            raise UserError(_('Only a payroll manager can set a confirmed payslip back to draft: %s',
                              ', '.join(confirmed.mapped(lambda payslip: payslip.number or payslip.name or ''))))
        return self.write({'state': 'draft'})

    def action_payslip_done(self):
        self._check_own_payslip()
        self.compute_sheet()
        return self.write({'state': 'done'})

    def action_payslip_cancel(self):
        self._check_own_payslip()
        return self.write({'state': 'cancel'})

    def refund_sheet(self):
        refunds = self.env['hr.payslip']
        for payslip in self:
            copied_payslip = payslip.copy({
                'credit_note': True,
                'name': _('Refund: %s', payslip.name or ''),
            })
            copied_payslip.compute_sheet()
            copied_payslip.action_payslip_done()
            refunds |= copied_payslip
        form_view_ref = self.env.ref('om_hr_payroll.view_hr_payslip_form', False)
        list_view_ref = self.env.ref('om_hr_payroll.view_hr_payslip_tree', False)
        return {
            'name': (_("Refund Payslip")),
            'view_mode': 'list,form',
            'res_model': 'hr.payslip',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'domain': [('id', 'in', refunds.ids)],
            'views': [(list_view_ref and list_view_ref.id or False, 'list'),
                      (form_view_ref and form_view_ref.id or False, 'form')],
            'context': {}
        }

    def action_send_payslips(self):
        """ Email their payslip to the employees, with the payslip attached: only the confirmed payslips are sent. """
        template = self.env.ref('om_hr_payroll.mail_template_payslip')
        payslips = self.filtered(lambda payslip: payslip.state == 'done')
        not_done = self - payslips
        without_email = payslips.filtered(lambda payslip: not payslip.employee_id.work_email)
        to_send = payslips - without_email
        if to_send:
            to_send.message_post_with_source(template, message_type='comment', subtype_xmlid='mail.mt_comment')
        message = _('%s payslip(s) sent.', len(to_send))
        if without_email:
            message += ' ' + _('Not sent, the employee has no work email: %s.',
                               ', '.join(without_email.mapped('employee_id.name')))
        if not_done:
            message += ' ' + _('Not sent, the payslip is not confirmed: %s.',
                               ', '.join(not_done.mapped(lambda payslip: payslip.number or payslip.name or '')))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'warning' if without_email or not_done or not to_send else 'success',
                'message': message,
                'sticky': bool(without_email or not_done),
            },
        }

    def action_send_email(self):
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        try:
            template_id = self.env.ref('om_hr_payroll.mail_template_payslip').id
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data._xmlid_lookup('mail.email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = {
            'default_model': 'hr.payslip',
            'default_res_ids': self.ids,
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
        }
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

    def check_done(self):
        return True

    def unlink(self):
        if any(self.filtered(lambda payslip: payslip.state not in ('draft', 'cancel'))):
            raise UserError(_('You cannot delete a payslip which is not draft or cancelled!'))
        return super().unlink()

    @api.model
    def get_versions(self, employee, date_from, date_to):
        """
        @param employee: recordset of employee
        @param date_from: date field
        @param date_to: date field
        @return: returns the ids of the versions of the employee in contract during the given dates, the version in
                 effect at the end of the period first. A version amended during the period is replaced by its
                 amendment: a payslip is computed with a single version.
        """
        versions = employee._get_versions_with_contract_overlap_with_period(
            fields.Date.to_date(date_from), fields.Date.to_date(date_to))
        return versions.sorted('date_version', reverse=True).ids

    def write(self, vals):
        # a confirmed or rejected payslip is a document: its amounts, employee and period do not change any more
        if not self._is_payroll_manager() and set(vals) - PAYSLIP_CLOSED_WRITABLE:
            closed = self.filtered(lambda payslip: payslip.state in ('done', 'cancel'))
            if closed:
                raise UserError(_('The payslip %s is confirmed: ask a payroll manager to change it.',
                                  closed[0].number or closed[0].name or ''))
        return super().write(vals)

    def compute_sheet(self):
        closed = self.filtered(lambda payslip: payslip.state in ('done', 'cancel'))
        if closed:
            raise UserError(_('The payslip %s is confirmed: set it back to draft before computing it again.',
                              closed[0].number or closed[0].name or ''))
        for payslip in self:
            number = payslip.number or self.env['ir.sequence'].next_by_code('salary.slip')
            # delete old payslip lines
            payslip.line_ids.unlink()

            version_ids = payslip.version_id.ids or \
                          self.get_versions(payslip.employee_id, payslip.date_from, payslip.date_to)[:1]

            if not version_ids:
                raise ValidationError(
                    _("No running version/contract found for the employee: %s or no version in the given period"
                      % payslip.employee_id.name))

            lines = [(0, 0, line) for line in self._get_payslip_lines(version_ids, payslip.id)]
            payslip.write({'line_ids': lines, 'number': number})
        return True

    @api.model
    def _get_year_start(self, date, company):
        """ :return: the day the payroll year of the company starts, for the year containing `date`

        The fiscal year of the company is used, so that the year to date follows what the company already
        declares in Odoo: April to March, July to June or the calendar year. Without accounting installed,
        there is no fiscal year to read and the calendar year is used.
        """
        if hasattr(company, 'compute_fiscalyear_dates'):
            return company.compute_fiscalyear_dates(date)['date_from']
        return date.replace(month=1, day=1)

    @api.model
    def _get_paid_rate(self, work_entry_type):
        """ :return: how much of a time off of this time type is paid: 1.0 in full, 0.0 not at all, 0.5 half

        A time type marked unpaid in the Time Off application is not paid whatever its rate, and a time off
        without a time type is taken as paid, so that nothing is deducted by surprise.
        """
        if not work_entry_type:
            return 1.0
        if 'unpaid' in work_entry_type._fields and work_entry_type.unpaid:
            return 0.0
        return work_entry_type.amount_rate

    @api.model
    def get_worked_day_lines(self, versions, date_from, date_to):
        """
        @param versions: Browse record of hr.version
        @return: returns a list of dict containing the input that should be applied
        """
        res = []
        for version in versions:
            calendar = version.resource_calendar_id or version.employee_id.resource_calendar_id
            if not calendar:
                continue

            day_from = datetime.combine(fields.Date.from_string(date_from), time.min)
            day_to = datetime.combine(fields.Date.from_string(date_to), time.max)

            # compute leave days
            leaves = {}
            tz = timezone(version.employee_id.tz or self.env.company.tz or 'UTC')
            day_leave_intervals = version.employee_id.list_leaves(day_from, day_to, calendar=calendar)
            for day, hours, leave in day_leave_intervals:
                holiday = leave.holiday_id
                work_entry_type = holiday.work_entry_type_id
                current_leave_struct = leaves.setdefault(work_entry_type, {
                    'name': work_entry_type.name or _('Global Leaves'),
                    'sequence': 5,
                    'code': work_entry_type.code or 'GLOBAL',
                    'number_of_days': 0.0,
                    'number_of_hours': 0.0,
                    'version_id': version.id,
                    'work_entry_type_id': work_entry_type.id,
                    # a time off without a time type is taken as paid: nothing is deducted for it
                    'paid_rate': self._get_paid_rate(work_entry_type),
                })
                current_leave_struct['number_of_hours'] -= hours
                work_hours = calendar.get_work_hours_count(
                    tz.localize(datetime.combine(day, time.min)),
                    tz.localize(datetime.combine(day, time.max)),
                    compute_leaves=False,
                )
                if work_hours:
                    current_leave_struct['number_of_days'] -= hours / work_hours

            # compute worked days
            work_data = version.employee_id._get_work_days_data(
                day_from,
                day_to,
                calendar=calendar,
                compute_leaves=False,
            )
            attendances = {
                'name': _("Normal Working Days paid at 100%"),
                'sequence': 1,
                'code': WORKED_DAYS_CODE,
                'number_of_days': work_data['days'],
                'number_of_hours': work_data['hours'],
                'version_id': version.id,
            }

            res.append(attendances)
            res.extend(leaves.values())
        return res

    @api.model
    def get_inputs(self, versions, date_from, date_to):
        res = []

        structure_ids = versions.mapped('struct_id').ids
        if not structure_ids:
            structure_ids = versions.mapped('employee_id.struct_id').ids

        rule_ids = self.env['hr.payroll.structure'].browse(structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence in sorted(rule_ids, key=lambda x: x[1])]
        inputs = self.env['hr.salary.rule'].browse(sorted_rule_ids).mapped('input_ids')

        for version in versions:
            for input in inputs:
                input_data = {
                    'name': input.name,
                    'code': input.code,
                    'version_id': version.id,
                }
                res += [input_data]
        return res

    @api.model
    def _get_payslip_lines(self, version_ids, payslip_id):

        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = category.code in localdict['categories'].dict and \
                                                          localdict['categories'].dict[category.code] + amount or amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, employee_id, dict, env):
                self.employee_id = employee_id
                self.dict = dict
                self.env = env

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.context_today(self.env['hr.payslip'])
                self.env.flush_all()
                self.env.cr.execute("""
                    SELECT sum(amount) as sum
                    FROM hr_payslip as hp, hr_payslip_input as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()[0] or 0.0

        class WorkedDays(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.context_today(self.env['hr.payslip'])
                self.env.flush_all()
                self.env.cr.execute("""
                    SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours
                    FROM hr_payslip as hp, hr_payslip_worked_days as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

            def scheduled_days(self):
                """ :return: the days the employee was due to work in the period, time off included """
                return sum(line.number_of_days for line in self.dict.values() if line.code == WORKED_DAYS_CODE)

            def unpaid_ratio(self):
                """ :return: the part of the period that the time off is not paid at, as a negative number

                The days of a time off are held negative, so 2 unpaid days out of 22 give -0.0909. Multiply
                it by the wage to get what has to be taken off the payslip.
                """
                scheduled = self.scheduled_days()
                if not scheduled:
                    return 0.0
                unpaid = sum(line.number_of_days * (1.0 - line.paid_rate)
                             for line in self.dict.values() if line.code != WORKED_DAYS_CODE)
                return unpaid / scheduled

        class Payslips(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.context_today(self.env['hr.payslip'])
                self.env.flush_all()
                self.env.cr.execute("""SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)
                            FROM hr_payslip as hp, hr_payslip_line as pl
                            WHERE hp.employee_id = %s AND hp.state = 'done'
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s""",
                                    (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

        result_dict = {}
        rules_dict = {}
        worked_days_dict = {}
        inputs_dict = {}
        blacklist = []
        payslip = self.env['hr.payslip'].browse(payslip_id)
        for worked_days_line in payslip.worked_days_line_ids:
            worked_days_dict[worked_days_line.code] = worked_days_line
        for input_line in payslip.input_line_ids:
            inputs_dict[input_line.code] = input_line

        categories = BrowsableObject(payslip.employee_id.id, {}, self.env)
        inputs = InputLine(payslip.employee_id.id, inputs_dict, self.env)
        worked_days = WorkedDays(payslip.employee_id.id, worked_days_dict, self.env)
        payslips = Payslips(payslip.employee_id.id, payslip, self.env)
        rules = BrowsableObject(payslip.employee_id.id, rules_dict, self.env)

        # the rates and the scales the rules read, as they stand at the end of the period being paid
        parameters = RuleParameters(self.env, payslip.date_to, payslip.company_id)
        brackets = SalaryBrackets(self.env, payslip.date_to, payslip.company_id)
        ytd = YearToDate(
            self.env, payslip.employee_id.id,
            self._get_year_start(payslip.date_to, payslip.company_id or self.env.company),
            payslip.date_to)

        baselocaldict = {'categories': categories, 'rules': rules, 'payslip': payslips, 'worked_days': worked_days,
                         'inputs': inputs, 'parameters': parameters, 'brackets': brackets, 'ytd': ytd}

        versions = self.env['hr.version'].browse(version_ids)

        if len(versions) == 1 and payslip.struct_id:
            structure_ids = list(set(payslip.struct_id._get_parent_structure().ids))
        else:
            structure_ids = versions.mapped('struct_id').ids or versions.mapped('employee_id.struct_id').ids

        rule_ids = self.env['hr.payroll.structure'].browse(structure_ids).get_all_rules()
        sorted_rule_ids = [id for id, sequence in sorted(rule_ids, key=lambda x: x[1])]
        sorted_rules = self.env['hr.salary.rule'].browse(sorted_rule_ids)

        for version in versions:
            employee = version.employee_id

            # salary rules access the version of the employee as `contract`, and the amounts set on it as
            # `components`, e.g. components.HOUSING
            components = BrowsableObject(
                employee.id,
                {line.code: line.amount for line in version.salary_component_ids if line.code},
                self.env)
            localdict = dict(baselocaldict, employee=employee, contract=version, components=components)

            for rule in sorted_rules:
                key = rule.code + '-' + str(version.id)
                localdict['result'] = None
                localdict['result_qty'] = 1.0
                localdict['result_rate'] = 100
                # check if the rule can be applied
                if rule._satisfy_condition(localdict) and rule.id not in blacklist:
                    # compute the amount of the rule
                    amount, qty, rate = rule._compute_rule(localdict)
                    # check if there is already a rule computed with that code
                    previous_amount = rule.code in localdict and localdict[rule.code] or 0.0

                    # set/overwrite the amount computed for this rule in the localdict
                    company = version.employee_id.company_id
                    tot_rule = company.currency_id.round(amount * qty * rate / 100.0)
                    localdict[rule.code] = tot_rule
                    rules_dict[rule.code] = rule

                    # sum the amount for its salary category
                    localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)

                    result_dict[key] = {
                        'salary_rule_id': rule.id,
                        'version_id': version.id,
                        'name': rule.name,
                        'code': rule.code,
                        'category_id': rule.category_id.id,
                        'sequence': rule.sequence,
                        'appears_on_payslip': rule.appears_on_payslip,
                        'condition_select': rule.condition_select,
                        'condition_python': rule.condition_python,
                        'condition_range': rule.condition_range,
                        'condition_range_min': rule.condition_range_min,
                        'condition_range_max': rule.condition_range_max,
                        'amount_select': rule.amount_select,
                        'amount_fix': rule.amount_fix,
                        'amount_python_compute': rule.amount_python_compute,
                        'amount_percentage': rule.amount_percentage,
                        'amount_percentage_base': rule.amount_percentage_base,
                        'register_id': rule.register_id.id,
                        'amount': amount,
                        'employee_id': version.employee_id.id,
                        'quantity': qty,
                        'rate': rate,
                    }
                else:
                    # blacklist this rule and its children
                    blacklist += [id for id, seq in rule._recursive_search_of_rules()]

        return list(result_dict.values())

    def onchange_employee_id(self, date_from, date_to, employee_id=False, contract_id=False):
        # defaults
        res = {
            'value': {
                'line_ids': [],
                # delete old input lines
                'input_line_ids': [(2, x,) for x in self.input_line_ids.ids],
                # delete old worked days lines
                'worked_days_line_ids': [(2, x,) for x in self.worked_days_line_ids.ids],
                'name': '',
                'version_id': False,
                'struct_id': False,
            }
        }
        if (not employee_id) or (not date_from) or (not date_to):
            return res
        ttyme = datetime.combine(fields.Date.from_string(date_from), time.min)
        employee = self.env['hr.employee'].browse(employee_id)
        locale = self.env.context.get('lang') or 'en_US'
        res['value'].update({
            'name': _('Salary Slip of %s for %s') % (employee.name, str(
                babel.dates.format_date(date=ttyme, format='MMMM-y', locale=locale))),
            'company_id': employee.company_id.id,
        })

        if not self.env.context.get('contract'):
            # fill with the first contract of the employee
            contract_ids = self.get_versions(employee, date_from, date_to)
        else:
            if contract_id:
                # set the list of contract for which the input have to be filled
                contract_ids = [contract_id]
            else:
                # if we don't give the contract, then the input to fill should be for all current contracts
                # of the employee
                contract_ids = self.get_versions(employee, date_from, date_to)

        if not contract_ids:
            return res
        contract = self.env['hr.version'].browse(contract_ids[0])
        res['value'].update({
            'version_id': contract.id
        })
        struct = contract.struct_id
        if not struct:
            return res
        res['value'].update({
            'struct_id': struct.id,
        })
        # computation of the salary input
        contracts = contract
        worked_days_line_ids = self.get_worked_day_lines(contracts, date_from, date_to)
        input_line_ids = self.get_inputs(contracts, date_from, date_to)
        res['value'].update({
            'worked_days_line_ids': worked_days_line_ids,
            'input_line_ids': input_line_ids,
        })
        return res

    @api.onchange('employee_id', 'date_from', 'date_to')
    def onchange_employee(self):
        self.ensure_one()
        if (not self.employee_id) or (not self.date_from) or (not self.date_to):
            return
        employee = self.employee_id
        date_from = self.date_from
        date_to = self.date_to
        version_ids = []

        ttyme = datetime.combine(fields.Date.from_string(date_from), time.min)
        locale = self.env.context.get('lang') or 'en_US'
        self.name = _('Salary Slip of %s for %s') % (employee.name, str(
            babel.dates.format_date(date=ttyme, format='MMMM-y', locale=locale)))
        self.company_id = employee.company_id

        if not self.env.context.get('version') or not self.version_id:
            version_ids = self.get_versions(employee, date_from, date_to)
            if not version_ids:
                return
            self.version_id = self.env['hr.version'].browse(version_ids[0])
        version_ids = self.version_id.ids

        if self.version_id.struct_id or employee.struct_id:
            self.struct_id = self.version_id.struct_id or employee.struct_id

        # computation of the salary input
        versions = self.env['hr.version'].browse(version_ids)
        if versions:
            worked_days_line_ids = self.get_worked_day_lines(versions, date_from, date_to)
            worked_days_lines = self.worked_days_line_ids.browse([])
            for r in worked_days_line_ids:
                worked_days_lines += worked_days_lines.new(r)
            self.worked_days_line_ids = worked_days_lines

            input_line_ids = self.get_inputs(versions, date_from, date_to)
            input_lines = self.input_line_ids.browse([])
            for r in input_line_ids:
                input_lines += input_lines.new(r)
            self.input_line_ids = input_lines
            return

    @api.onchange('version_id')
    def onchange_version(self):
        if not self.version_id:
            self.struct_id = False
        self.with_context(version=True).onchange_employee()
        return

    def get_salary_line_total(self, code):
        self.ensure_one()
        line = self.line_ids.filtered(lambda line: line.code == code)
        if line:
            return line[0].total
        else:
            return 0.0


class HrPayslipLine(models.Model):
    _name = 'hr.payslip.line'
    _inherit = 'hr.salary.rule'
    _description = 'Payslip Line'
    _order = 'version_id, sequence'

    slip_id = fields.Many2one('hr.payslip', string='Pay Slip', required=True, ondelete='cascade')
    salary_rule_id = fields.Many2one('hr.salary.rule', string='Rule', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    version_id = fields.Many2one('hr.version', string='Version/Contract', required=True, index=True)
    rate = fields.Float(string='Rate (%)', default=100.0)
    amount = fields.Float()
    quantity = fields.Float(default=1.0)
    # stored: the totals of the payslips already paid are summed in SQL, by the year to date and by
    # payslip.sum() in the salary rules
    total = fields.Float(compute='_compute_total', string='Total', store=True)

    @api.depends('quantity', 'amount', 'rate')
    def _compute_total(self):
        for line in self:
            line.total = float(line.quantity) * line.amount * line.rate / 100

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if 'employee_id' not in values or 'version_id' not in values:
                payslip = self.env['hr.payslip'].browse(values.get('slip_id'))
                values['employee_id'] = values.get('employee_id') or payslip.employee_id.id
                values['version_id'] = values.get('version_id') or payslip.version_id.id
        # the lines copy the salary rules, chatter included: they keep no followers, messages nor tracking
        lines = super(HrPayslipLine, self.with_context(tracking_disable=True)).create(vals_list)
        lines._check_payslip_open()
        return lines.with_env(self.env)

    def write(self, vals):
        self._check_payslip_open()
        return super(HrPayslipLine, self.with_context(tracking_disable=True)).write(vals)

    def _track_get_fields(self):
        return set()

    def unlink(self):
        self._check_payslip_open()
        return super().unlink()

    def _check_payslip_open(self):
        """ The lines of a confirmed payslip are what was paid: only a payroll manager changes them. """
        if self.env['hr.payslip']._is_payroll_manager():
            return
        closed = self.slip_id.filtered(lambda payslip: payslip.state in ('done', 'cancel'))
        if closed:
            raise UserError(_('The payslip %s is confirmed: its lines cannot be changed.',
                              closed[0].number or closed[0].name or ''))


class HrPayslipWorkedDays(models.Model):
    _name = 'hr.payslip.worked_days'
    _description = 'Payslip Worked Days'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one('hr.payslip', string='Pay Slip', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, index=True, default=10)
    code = fields.Char(required=True, help="The code that can be used in the salary rules")
    number_of_days = fields.Float(string='Number of Days')
    number_of_hours = fields.Float(string='Number of Hours')
    version_id = fields.Many2one('hr.version', string='Version/Contract', required=True,
                                 help="The version for which applied this input")
    work_entry_type_id = fields.Many2one('hr.work.entry.type', string='Time Type')
    paid_rate = fields.Float(
        string='Paid Rate', default=1.0,
        help='The part of the days that is paid, from the time type of the time off: 1 for a time off paid '
             'in full, 0 for an unpaid one, 0.5 for a time off paid at half.')


class HrPayslipInput(models.Model):
    _name = 'hr.payslip.input'
    _description = 'Payslip Input'
    _order = 'payslip_id, sequence'

    name = fields.Char(string='Description', required=True)
    payslip_id = fields.Many2one('hr.payslip', string='Pay Slip', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, index=True, default=10)
    code = fields.Char(required=True, help="The code that can be used in the salary rules")
    amount = fields.Float(help="Amount used in computation")
    version_id = fields.Many2one('hr.version', string='Version/Contract', required=True,
                                 help="The version for which applied this input")


class HrPayslipRun(models.Model):
    _name = 'hr.payslip.run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Payslip Batches'

    name = fields.Char(required=True, tracking=True)
    slip_ids = fields.One2many('hr.payslip', 'payslip_run_id', string='Payslips')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('close', 'Close'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft', tracking=True)
    date_start = fields.Date(
        string='Date From', required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        tracking=True
    )
    date_end = fields.Date(
        string='Date To', required=True,
        default=lambda self: fields.Date.context_today(self) + relativedelta(day=31),
        tracking=True
    )
    credit_note = fields.Boolean(string='Credit Note',
                                 help="If its checked, indicates that all payslips generated from here are refund "
                                      "payslips.", tracking=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    def draft_payslip_run(self):
        return self.write({'state': 'draft'})

    def close_payslip_run(self):
        return self.write({'state': 'close'})

    def action_send_payslips(self):
        """ Email their confirmed payslip to the employees of the batch, with the payslip attached. """
        self.ensure_one()
        return self.slip_ids.filtered(lambda payslip: payslip.state == 'done').action_send_payslips()

    def action_open_payroll_analysis(self):
        """ The amounts of the payslips of the batch, by employee and by category of rule. """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_hr_payroll.action_hr_payslip_analysis')
        action['display_name'] = _('Payroll Analysis: %s', self.name)
        action['domain'] = [('payslip_run_id', '=', self.id)]
        action['context'] = {
            'search_default_not_cancelled': 1,
            'pivot_row_groupby': ['employee_id'],
            'pivot_column_groupby': ['category_id'],
            'graph_groupbys': ['employee_id', 'category_id'],
        }
        return action

    def done_payslip_run(self):
        # the payslips already confirmed or rejected keep their status and their amounts
        self.slip_ids.filtered(lambda payslip: payslip.state in ('draft', 'verify')).action_payslip_done()
        return self.write({'state': 'done'})

    def unlink(self):
        if any(self.filtered(lambda payslip_run: payslip_run.state not in ('draft'))):
            raise UserError(_('You cannot delete a payslip batch which is not draft!'))
        return super().unlink()
