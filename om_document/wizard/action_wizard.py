from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class DocumentsActionWizard(models.TransientModel):
    _name = 'om.documents.action.wizard'
    _description = 'Run a Document Action'

    document_ids = fields.Many2many('om.documents.document', string='Documents')
    available_action_ids = fields.Many2many('om.documents.action', compute='_compute_available_action_ids')
    action_id = fields.Many2one('om.documents.action', string='Action',
                                domain="[('id', 'in', available_action_ids)]")

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        if self.env.context.get('active_model') == 'om.documents.document':
            values['document_ids'] = [Command.set(self.env.context.get('active_ids') or [])]
        return values

    @api.depends('document_ids')
    def _compute_available_action_ids(self):
        for wizard in self:
            wizard.available_action_ids = self.env['om.documents.action']._get_available(wizard.document_ids._origin)

    def action_run(self):
        self.ensure_one()
        if not self.action_id:
            raise UserError(self.env._('Choose the action to run.'))
        return self.action_id.run(self.document_ids)
