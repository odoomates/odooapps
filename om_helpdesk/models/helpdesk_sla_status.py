from odoo import api, fields, models


class OmHelpdeskSlaStatus(models.Model):
    _name = 'om.helpdesk.sla.status'
    _description = 'Ticket SLA Status'
    _order = 'deadline, id'
    _rec_name = 'sla_id'

    ticket_id = fields.Many2one('om.helpdesk.ticket', string='Ticket', required=True, index=True, ondelete='cascade')
    sla_id = fields.Many2one('om.helpdesk.sla', string='SLA Policy', required=True, index=True, ondelete='cascade')
    sla_stage_id = fields.Many2one(related='sla_id.stage_id', string='Target Stage', store=True)
    team_id = fields.Many2one(related='ticket_id.team_id', store=True, index=True)
    user_id = fields.Many2one(related='ticket_id.user_id', string='Assigned To', store=True)
    priority = fields.Selection(related='ticket_id.priority', store=True)
    ticket_type_id = fields.Many2one(related='ticket_id.ticket_type_id', store=True)
    partner_id = fields.Many2one(related='ticket_id.partner_id', string='Customer', store=True)
    company_id = fields.Many2one(related='ticket_id.company_id', store=True, index=True)
    deadline = fields.Datetime(index=True)
    reached_datetime = fields.Datetime(string='Reached On')
    status = fields.Selection([
        ('ongoing', 'Ongoing'),
        ('reached', 'Reached'),
        ('failed', 'Failed'),
    ], compute='_compute_status', store=True, index=True)
    success_rate = fields.Float(
        string='Success Rate (%)', compute='_compute_status', store=True, aggregator='avg',
        help="100 when the SLA was reached in time, 0 when it failed. Ongoing lines count as 100 until their deadline passes.")
    exceeded_hours = fields.Float(
        string='Delay (Hours)', compute='_compute_status', store=True, aggregator='avg',
        help="Hours between the deadline and the moment the target stage was reached, or now when still not reached.")

    @api.depends('deadline', 'reached_datetime')
    def _compute_status(self):
        now = fields.Datetime.now()
        for line in self:
            end = line.reached_datetime or now
            if line.deadline and end > line.deadline:
                line.status = 'failed'
                line.exceeded_hours = (end - line.deadline).total_seconds() / 3600
            else:
                line.status = 'reached' if line.reached_datetime else 'ongoing'
                line.exceeded_hours = 0.0
            line.success_rate = 0.0 if line.status == 'failed' else 100.0

    @api.model
    def _cron_check_deadlines(self):
        """ Flag ongoing SLAs whose deadline passed: status is stored, the clock is not a dependency. """
        lines = self.search([('status', '=', 'ongoing'), ('deadline', '<', fields.Datetime.now())])
        if not lines:
            return True
        self.env.add_to_compute(self._fields['status'], lines)
        lines._recompute_recordset(['status', 'success_rate', 'exceeded_hours'])
        tickets = lines.ticket_id
        ticket_fields = ['sla_deadline', 'sla_fail', 'sla_success', 'sla_state']
        for fname in ticket_fields:
            self.env.add_to_compute(tickets._fields[fname], tickets)
        tickets._recompute_recordset(ticket_fields)
        return True
