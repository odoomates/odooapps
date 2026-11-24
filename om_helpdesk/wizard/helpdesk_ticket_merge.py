from odoo import api, fields, models
from odoo.exceptions import UserError


class OmHelpdeskTicketMerge(models.TransientModel):
    _name = 'om.helpdesk.ticket.merge'
    _description = 'Merge Helpdesk Tickets'

    ticket_ids = fields.Many2many('om.helpdesk.ticket', string='Tickets to Merge', required=True)
    target_ticket_id = fields.Many2one(
        'om.helpdesk.ticket', string='Merge Into', required=True,
        compute='_compute_target_ticket_id', store=True, readonly=False,
        domain="[('id', 'in', ticket_ids)]")
    user_id = fields.Many2one(
        'res.users', string='Assign To', domain="[('share', '=', False)]",
        compute='_compute_target_values', store=True, readonly=False)
    team_id = fields.Many2one(
        'om.helpdesk.team', string='Team',
        compute='_compute_target_values', store=True, readonly=False)

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if self.env.context.get('active_model') == 'om.helpdesk.ticket' and self.env.context.get('active_ids'):
            res['ticket_ids'] = [(6, 0, self.env.context['active_ids'])]
        return res

    @api.depends('ticket_ids')
    def _compute_target_ticket_id(self):
        for wizard in self:
            if wizard.target_ticket_id not in wizard.ticket_ids._origin:
                wizard.target_ticket_id = wizard.ticket_ids._origin.sorted('id')[:1]

    @api.depends('target_ticket_id')
    def _compute_target_values(self):
        for wizard in self:
            wizard.user_id = wizard.target_ticket_id.user_id
            wizard.team_id = wizard.target_ticket_id.team_id

    def action_merge(self):
        self.ensure_one()
        tickets = self.ticket_ids
        if len(tickets) < 2:
            raise UserError(self.env._("Select at least two tickets to merge."))
        target = self.target_ticket_id
        if target not in tickets:
            raise UserError(self.env._("The ticket to merge into must be one of the selected tickets."))
        tickets._merge_into(target)
        values = {}
        if self.team_id and self.team_id != target.team_id:
            values['team_id'] = self.team_id.id
        if self.user_id != target.user_id:
            values['user_id'] = self.user_id.id
        if values:
            target.write(values)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.helpdesk.ticket',
            'res_id': target.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }
