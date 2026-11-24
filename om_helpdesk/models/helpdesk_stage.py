from odoo import fields, models


class OmHelpdeskStage(models.Model):
    _name = 'om.helpdesk.stage'
    _description = 'Helpdesk Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    team_ids = fields.Many2many(
        'om.helpdesk.team', 'om_helpdesk_stage_team_rel', 'stage_id', 'team_id', string='Teams',
        help="Teams using this stage. A stage without team is not proposed to new teams.")
    fold = fields.Boolean(string='Folded in Kanban', help="Folded stages are collapsed in the kanban view.")
    is_close = fields.Boolean(
        string='Closing Stage',
        help="Tickets in this stage are considered closed: the close date is set, "
             "and a rating is requested when the team asks for ratings.")
    template_id = fields.Many2one(
        'mail.template', string='Email Template', domain="[('model', '=', 'om.helpdesk.ticket')]",
        help="Email sent to the customer when the ticket reaches this stage.")
    legend_blocked = fields.Char(string='Blocked Label', default=lambda self: self.env._('Blocked'), translate=True, required=True)
    legend_done = fields.Char(string='Ready Label', default=lambda self: self.env._('Ready'), translate=True, required=True)
    legend_normal = fields.Char(string='In Progress Label', default=lambda self: self.env._('In Progress'), translate=True, required=True)
    ticket_count = fields.Integer(compute='_compute_ticket_count', string='Tickets')

    def _compute_ticket_count(self):
        data = dict(self.env['om.helpdesk.ticket']._read_group(
            [('stage_id', 'in', self.ids)], ['stage_id'], ['__count']))
        for stage in self:
            stage.ticket_count = data.get(stage, 0)
