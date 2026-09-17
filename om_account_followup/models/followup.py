from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FollowupFollowup(models.Model):
    _name = 'followup.followup'
    _description = 'Follow-up Plan'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, default=lambda self: self.env.company.name)
    sequence = fields.Integer(default=10)
    is_default = fields.Boolean(
        string='Default Plan',
        help='The plan of the customers of the company who have no plan of their own.')
    followup_line = fields.One2many('followup.line', 'followup_id', 'Follow-up', copy=True)
    company_id = fields.Many2one('res.company', 'Company', required=True, default=lambda self: self.env.company)
    auto_send = fields.Boolean(
        string='Send Automatically',
        help='Every day, send the reminders that are due: update the follow-up levels, send the emails and '
             'schedule the manual actions. Letters are not printed automatically: print them from the customers.')
    auto_user_id = fields.Many2one(
        'res.users', string='Send As', default=lambda self: self.env.user,
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help='The follow-up emails are sent in the name of this user, with the access rights of this user.')
    last_auto_send = fields.Date(string='Last Automatic Sending', readonly=True, copy=False)
    partner_count = fields.Integer(string='Customers', compute='_compute_partner_count')

    @api.constrains('auto_send', 'auto_user_id')
    def _check_auto_user(self):
        for followup in self:
            if followup.auto_send and not followup.auto_user_id:
                raise ValidationError(_('Choose the user sending the automatic follow-ups.'))

    @api.constrains('is_default', 'company_id')
    def _check_one_default(self):
        for company in self.filtered('is_default').company_id:
            if self.search_count([('company_id', '=', company.id), ('is_default', '=', True)]) > 1:
                raise ValidationError(_('The company %s already has a default follow-up plan.', company.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_default'):
                company_id = vals.get('company_id') or self.env.company.id
                self.search([('company_id', '=', company_id), ('is_default', '=', True)]).write(
                    {'is_default': False})
        plans = super().create(vals_list)
        # the first plan of a company is its default plan
        for plan in plans:
            if not plan.is_default and not self.search_count(
                    [('company_id', '=', plan.company_id.id), ('is_default', '=', True)]):
                plan.is_default = True
        return plans

    def write(self, vals):
        if vals.get('is_default'):
            # one default plan per company: the other plans of the company stop being the default
            companies = self.company_id if 'company_id' not in vals else self.env['res.company'].browse(
                vals['company_id'])
            self.search([('company_id', 'in', companies.ids), ('is_default', '=', True),
                         ('id', 'not in', self.ids)]).write({'is_default': False})
        return super().write(vals)

    def _compute_partner_count(self):
        Partner = self.env['res.partner']
        for plan in self:
            partners = Partner.with_company(plan.company_id).search_count([('followup_plan_id', '=', plan.id)])
            plan.partner_count = partners

    @api.model
    def _get_default_plan(self, company=None):
        company = company or self.env.company
        return self.search([('company_id', '=', company.id)], order='is_default desc, sequence, id', limit=1)

    def _get_levels(self):
        """ :return: the levels of the plan, from the first to the last """
        self.ensure_one()
        return self.followup_line.sorted(lambda line: (line.delay, line.id))

    @api.model
    def _create_default_plans(self, companies):
        """ A plan with three reminders for the companies without any plan """
        for company in companies:
            if self.sudo().search_count([('company_id', '=', company.id)]):
                continue
            templates = [self.env.ref('om_account_followup.email_template_om_account_followup_level%s' % index,
                                      raise_if_not_found=False) for index in range(3)]
            self.sudo().create({
                'name': company.name,
                'company_id': company.id,
                'is_default': True,
                'followup_line': [
                    (0, 0, {
                        'name': _('Friendly reminder'), 'delay': 7, 'send_email': True, 'send_letter': False,
                        'email_template_id': templates[0].id if templates[0] else False,
                    }),
                    (0, 0, {
                        'name': _('Second reminder'), 'delay': 21, 'send_email': True, 'send_letter': True,
                        'email_template_id': templates[1].id if templates[1] else False,
                    }),
                    (0, 0, {
                        'name': _('Final notice'), 'delay': 45, 'send_email': True, 'send_letter': True,
                        'manual_action': True, 'manual_action_note': _('Call the customer about the overdue '
                                                                        'invoices.'),
                        'email_template_id': templates[2].id if templates[2] else False,
                    }),
                ],
            })

    def action_open_partners(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_account_followup.action_customer_followup')
        action['domain'] = [('followup_plan_id', '=', self.id)]
        action['context'] = {'search_default_filter_action_needed': False}
        return action

    @api.model
    def _cron_send_followups(self):
        """ Daily job: send the reminders that are due for the plans sending them automatically. """
        today = fields.Date.context_today(self)
        for followup in self.search([('auto_send', '=', True)]):
            if followup.last_auto_send == today:
                continue
            wizard = self.env['followup.print'].with_user(followup.auto_user_id).with_company(followup.company_id)
            wizard.with_context(followup_automatic=True).create({
                'followup_id': followup.id,
                'date': today,
            }).do_process()
            followup.last_auto_send = today


class FollowupLine(models.Model):
    _name = 'followup.line'
    _description = 'Follow-up Criteria'
    _order = 'delay'

    def _compute_sequence(self):
        delays = [line.delay for line in self.followup_id.followup_line]
        delays.sort()
        for line in self.followup_id.followup_line:
            sequence = delays.index(line.delay)
            line.sequence = sequence+1

    @api.model
    def default_get(self, default_fields):
        values = super().default_get(default_fields)
        template = self.env.ref('om_account_followup.email_template_om_account_followup_default',
                                raise_if_not_found=False)
        if template and 'email_template_id' in default_fields:
            values.setdefault('email_template_id', template.id)
        return values

    name = fields.Char('Follow-Up Action', required=True)
    sequence = fields.Integer('Sequence', compute='_compute_sequence',
                              store=False,
                              help="Gives the sequence order when displaying a list of follow-up lines.")
    followup_id = fields.Many2one('followup.followup', 'Follow Ups',
                                  required=True, ondelete="cascade")
    delay = fields.Integer('Due Days',
                           help="The number of days after the due date of the "
                                "invoice to wait before sending the reminder. Could be negative if you want "
                                "to send a polite alert beforehand.",
                           required=True)
    description = fields.Text('Printed Message', translate=True, default="""
        Dear %(partner_name)s,

Exception made if there was a mistake of ours, it seems that the following
amount stays unpaid. Please, take appropriate measures in order to carry out
this payment in the next 8 days.

Would your payment have been carried out after this mail was sent, please
ignore this message. Do not hesitate to contact our accounting department.

Best Regards,
""", )
    send_email = fields.Boolean('Send an Email', default=True,
                                help="When processing, it will send an email")
    send_letter = fields.Boolean('Send a Letter', default=True,
                                 help="When processing, it will print a letter")
    manual_action = fields.Boolean('Manual Action', default=False,
                                   help="When processing, it will set the "
                                        "manual action to be taken for that customer. ")
    manual_action_note = fields.Text('Action To Do')
    manual_action_responsible_id = fields.Many2one('res.users',
                                                   string='Assign a Responsible', ondelete='set null')
    email_template_id = fields.Many2one('mail.template', 'Email Template',
                                        ondelete='set null')

    _days_uniq = models.Constraint(
        'unique(followup_id, delay)',
        'Days of the follow-up levels must be different',
    )

    @api.constrains('description')
    def _check_description(self):
        for line in self:
            if line.description:
                try:
                    line.description % {'partner_name': '', 'date': '',
                                        'user_signature': '',
                                        'company_name': ''}
                except (KeyError, TypeError, ValueError):
                    raise ValidationError(
                        _('Your description is invalid, use the right legend '
                          'or %% if you want to use the percent character.'))
