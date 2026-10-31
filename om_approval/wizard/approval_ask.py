from odoo import api, fields, models
from odoo.exceptions import UserError


class ApprovalAsk(models.TransientModel):
    """ The click on a button needing an approval: the requester says why, with files, then the approval is
    asked for each record selected. """
    _name = 'approval.ask'
    _description = 'Ask for Approval'

    res_model = fields.Char(required=True)
    method = fields.Char(required=True)
    res_ids = fields.Json(required=True, help='The records to ask the approval for.')
    all_ids = fields.Json(help='All the records the button was clicked for.')
    approved_ids = fields.Json(help='The requests already approved, letting the button run.')
    waiting_ids = fields.Json(help='The requests already asked and waiting.')
    message = fields.Text(readonly=True)
    note_required = fields.Boolean(readonly=True)
    note = fields.Text(string='Why')
    attachment_ids = fields.Many2many('ir.attachment', 'approval_ask_attachment_rel', 'ask_id', 'attachment_id',
                                      string='Files')
    summary = fields.Text(compute='_compute_summary')

    @api.depends('res_model', 'res_ids', 'waiting_ids')
    def _compute_summary(self):
        for wizard in self:
            lines = []
            if wizard.res_model in self.env and wizard.res_ids:
                names = self.env[wizard.res_model].browse(wizard.res_ids).exists().mapped('display_name')
                lines.append(self.env._('Approval asked for: %s', ', '.join(names)))
            requests = self.env['approval.request'].sudo().browse(wizard.waiting_ids or []).exists()
            for request in requests:
                lines.append(self.env._('%(record)s already waits for %(step)s (%(request)s).',
                                        record=request.document_name, step=request.approval_step,
                                        request=request.name))
            wizard.summary = '\n'.join(lines)

    def action_ask(self):
        """ Ask the approvals; when they are all approved at once, run the button. """
        self.ensure_one()
        if self.note_required and not (self.note or '').strip():
            raise UserError(self.env._('Write why the approval is needed.'))
        Request = self.env['approval.request']
        records = self.env[self.res_model].browse(self.res_ids).exists()
        records.check_access('read')
        flows = self.env['approval.rule']
        asked = []
        for index, record in enumerate(records):
            flow = flows._get_flow(record, self.method)
            if not flow:
                continue
            # each request keeps its own copy of the files
            files = self.attachment_ids if index == 0 else self.env['ir.attachment'].union(
                *[attachment.copy() for attachment in self.attachment_ids])
            asked.append((record, Request._request(record, flow, method=self.method,
                                                   button_name=flow.button_id.name, note=self.note,
                                                   attachments=files.sudo())))
        waiting = [(request._record(), request)
                   for request in Request.sudo().browse(self.waiting_ids or []).exists()
                   if request.state == 'to_approve']
        blocked = waiting + [(record, request) for record, request in asked if request.state != 'approved']
        if blocked:
            return Request._notify_blocked(blocked, {request for _record, request in asked})
        # approved at once, e.g. by a requester approving every step: the button runs now, for all the records
        approved = Request.browse([request.id for _record, request in asked] + (self.approved_ids or []))
        Request._consume(approved.sudo().filtered(lambda r: r.state == 'approved'))
        try:
            result = getattr(self.env[self.res_model].browse(self.all_ids or self.res_ids).exists(), self.method)()
        finally:
            Request._restore_lock()
        return result if isinstance(result, dict) else {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        for wizard in wizards:
            wizard.attachment_ids.sudo().write({'res_model': self._name, 'res_id': wizard.id})
        return wizards

    def write(self, vals):
        result = super().write(vals)
        if 'attachment_ids' in vals:
            self.attachment_ids.sudo().write({'res_model': self._name, 'res_id': self.id})
        return result
