from odoo import api, fields, models


class ApprovalDecide(models.TransientModel):
    """ Approve or refuse a step, with the note the flow asks for. """
    _name = 'approval.decide'
    _description = 'Approve or Refuse'

    request_id = fields.Many2one('approval.request', required=True, ondelete='cascade')
    decision = fields.Selection([('approve', 'Approve'), ('refuse', 'Refuse')], required=True, default='refuse')
    note_mode = fields.Selection([('none', 'Not Asked'), ('optional', 'Optional'), ('required', 'Required')],
                                 compute='_compute_note_mode')
    note = fields.Text()

    @api.depends('request_id', 'decision')
    def _compute_note_mode(self):
        for wizard in self:
            flow = wizard.request_id.sudo().flow_id
            if not flow:
                wizard.note_mode = 'required' if wizard.decision == 'refuse' else 'none'
            else:
                wizard.note_mode = flow[f'{wizard.decision}_note']

    def action_confirm(self):
        self.ensure_one()
        if self.decision == 'approve':
            self.request_id.action_approve(self.note)
        else:
            self.request_id.action_refuse(self.note)
        return {'type': 'ir.actions.act_window_close'}
