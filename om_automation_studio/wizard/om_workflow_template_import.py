import json

from odoo import fields, models
from odoo.exceptions import UserError


class OmWorkflowTemplateImport(models.TransientModel):
    _name = 'om.workflow.template.import'
    _description = 'Import a Workflow Template'

    file = fields.Binary(required=True)
    filename = fields.Char()

    def action_import(self):
        self.ensure_one()
        try:
            data = json.loads(self.file.content)
        except (ValueError, UnicodeDecodeError) as error:
            raise UserError(self.env._("This file is not a workflow template.")) from error
        template = self.env['om.workflow.template']._import_data(data)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.workflow.template',
            'res_id': template.id,
            'view_mode': 'form',
            'target': 'current',
        }
