from odoo import api, fields, models
from odoo.fields import Command


class DocumentsMoveWizard(models.TransientModel):
    _name = 'om.documents.move.wizard'
    _description = 'Move or Tag Documents'

    document_ids = fields.Many2many('om.documents.document', string='Documents')
    folder_id = fields.Many2one('om.documents.folder', string='Move To')
    add_tag_ids = fields.Many2many('om.documents.tag', 'om_documents_move_wizard_add_tag_rel', string='Add Tags')
    remove_tag_ids = fields.Many2many('om.documents.tag', 'om_documents_move_wizard_remove_tag_rel',
                                      string='Remove Tags')
    owner_id = fields.Many2one('res.users', string='Set Owner', domain=[('share', '=', False)])
    partner_id = fields.Many2one('res.partner', string='Set Contact')

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        if self.env.context.get('active_model') == 'om.documents.document':
            values['document_ids'] = [Command.set(self.env.context.get('active_ids') or [])]
        return values

    def action_apply(self):
        self.ensure_one()
        values = {}
        if self.folder_id:
            values['folder_id'] = self.folder_id.id
        if self.owner_id:
            values['owner_id'] = self.owner_id.id
        if self.partner_id:
            values['partner_id'] = self.partner_id.id
        commands = [Command.link(tag.id) for tag in self.add_tag_ids] + \
                   [Command.unlink(tag.id) for tag in self.remove_tag_ids]
        if commands:
            values['tag_ids'] = commands
        if values:
            self.document_ids.write(values)
        return {'type': 'ir.actions.act_window_close'}
