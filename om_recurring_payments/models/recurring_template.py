from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountRecurringTemplate(models.Model):
    _name = 'account.recurring.template'
    _inherit = ['mail.thread']
    _description = 'Recurring Template'
    _rec_name = 'name'
    _check_company_auto = True

    name = fields.Char('Name', required=True)
    journal_id = fields.Many2one('account.journal', 'Journal', required=True, check_company=True,
                                 domain=[('type', 'in', ('bank', 'cash'))], tracking=True)
    recurring_period = fields.Selection(selection=[('days', 'Days'),
                                                   ('weeks', 'Weeks'),
                                                   ('months', 'Months'),
                                                   ('years', 'Years')], required=True, tracking=True)
    description = fields.Text('Description')
    state = fields.Selection(selection=[('draft', 'Draft'),
                                        ('done', 'Done')], default='draft', string='Status', tracking=True)
    journal_state = fields.Selection(selection=[('draft', 'Un Posted'),
                                                ('posted', 'Posted')],
                                     required=True, default='draft', string='Generate Journal As', tracking=True)
    recurring_interval = fields.Integer('Recurring Interval', default=1, required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id)

    @api.constrains('recurring_interval')
    def _check_recurring_interval(self):
        for rec in self:
            if rec.recurring_interval <= 0:
                raise ValidationError(_('The recurring interval must be a positive number.'))

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_done(self):
        for rec in self:
            rec.state = 'done'
