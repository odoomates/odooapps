from datetime import timedelta, timezone

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .helpdesk_ticket import TICKET_PRIORITY


class OmHelpdeskSla(models.Model):
    _name = 'om.helpdesk.sla'
    _description = 'Helpdesk SLA Policy'
    _order = 'team_id, sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Html(translate=True)
    team_id = fields.Many2one('om.helpdesk.team', string='Team', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='team_id.company_id', store=True, index=True)
    priority = fields.Selection(
        TICKET_PRIORITY, string='Minimum Priority', required=True, default='0',
        help="The policy applies to tickets with this priority or higher.")
    ticket_type_ids = fields.Many2many(
        'om.helpdesk.ticket.type', string='Ticket Types',
        help="Leave empty to apply the policy to every ticket type.")
    tag_ids = fields.Many2many(
        'om.helpdesk.tag', string='Tags',
        help="The policy applies to tickets that have at least one of these tags. Leave empty for all tickets.")
    partner_ids = fields.Many2many(
        'res.partner', string='Customers',
        help="The policy applies to tickets of these customers (and their contacts). Leave empty for all customers.")
    stage_id = fields.Many2one(
        'om.helpdesk.stage', string='Target Stage', required=True,
        help="The SLA is reached when the ticket reaches this stage or a later one.")
    time = fields.Float(
        string='Time to Reach', required=True, default=4.0,
        help="Maximum time, in hours, between the creation of the ticket and the target stage.")
    time_mode = fields.Selection([
        ('working', 'Working hours'),
        ('calendar', 'Calendar hours'),
    ], string='Count In', required=True, default='working',
        help="Working hours: only the working time of the team calendar counts.\n"
             "Calendar hours: every hour counts, nights and weekends included.")
    status_ids = fields.One2many('om.helpdesk.sla.status', 'sla_id', string='Status Lines')
    ticket_count = fields.Integer(compute='_compute_ticket_count', string='Tickets')

    @api.constrains('time')
    def _check_time(self):
        if any(sla.time <= 0 for sla in self):
            raise ValidationError(self.env._("The time to reach an SLA must be positive."))

    def _compute_ticket_count(self):
        data = dict(self.env['om.helpdesk.sla.status']._read_group(
            [('sla_id', 'in', self.ids)], ['sla_id'], ['__count']))
        for sla in self:
            sla.ticket_count = data.get(sla, 0)

    def _applies_to(self, ticket):
        """ Whether this policy applies to the given ticket. """
        self.ensure_one()
        if ticket.team_id != self.team_id or not self.active:
            return False
        if int(ticket.priority or '0') < int(self.priority):
            return False
        if self.ticket_type_ids and ticket.ticket_type_id not in self.ticket_type_ids:
            return False
        if self.tag_ids and not (self.tag_ids & ticket.tag_ids):
            return False
        if self.partner_ids:
            commercial = ticket.partner_id.commercial_partner_id
            if not ticket.partner_id or not (ticket.partner_id in self.partner_ids or commercial in self.partner_ids):
                return False
        return True

    def _compute_deadline(self, start):
        """ Deadline of this policy for a ticket opened at `start` (naive UTC datetime). """
        self.ensure_one()
        calendar = self.team_id.resource_calendar_id
        if self.time_mode == 'calendar' or not calendar:
            return start + timedelta(hours=self.time)
        deadline = calendar.plan_hours(self.time, start.replace(tzinfo=timezone.utc), compute_leaves=True)
        if not deadline:
            return start + timedelta(hours=self.time)
        return deadline.astimezone(timezone.utc).replace(tzinfo=None)

    def action_view_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_helpdesk.action_helpdesk_ticket')
        action['domain'] = [('sla_status_ids.sla_id', '=', self.id)]
        action['context'] = {'default_team_id': self.team_id.id}
        action['display_name'] = self.name
        return action
