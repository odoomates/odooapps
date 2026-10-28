import base64
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.om_automation_studio.tools import check_graph
from odoo.addons.om_automation_studio.tools.portable import (
    FORMAT,
    VERSION,
    export_graph,
    import_graph,
)


class OmWorkflowTemplate(models.Model):
    """ A workflow kept to start others from: saved from a workflow of the
    company, or imported from a file. It appears among the templates of New. """
    _name = 'om.workflow.template'
    _description = 'Workflow Template'
    _order = 'name, id'

    name = fields.Char(required=True)
    description = fields.Text()
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=[('transient', '=', False)])
    model = fields.Char(related='model_id.model', string='Model Name', store=True)
    graph = fields.Json(copy=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company,
                                 help="Empty: shared with every company.")
    import_note = fields.Text('To Check', readonly=True,
                              help="What the imported file referred to and this database does not have.")
    export_file = fields.Binary(compute='_compute_export_file')

    def _compute_export_file(self):
        for template in self:
            data = json.dumps(template._export_data(), indent=2, ensure_ascii=False).encode()
            template.export_file = base64.b64encode(data)

    def _export_filename(self):
        return f"{(self.name or 'workflow').replace('/', '-')}.json"

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def action_create_workflow(self):
        self.ensure_one()
        return self.create_workflow()

    def action_export(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/export_file?download=true&filename={self._export_filename()}',
            'target': 'download',
        }

    def action_import(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Import a Workflow Template"),
            'res_model': 'om.workflow.template.import',
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # the template dialog
    # ------------------------------------------------------------------

    @api.model
    def gallery_list(self):
        """ The saved templates of the models this database has. """
        self.env['om.workflow'].check_access_rights('create')
        return [{
            'id': template.id,
            'name': template.name,
            'description': template.description or '',
            'model': template.model,
            'model_name': template.model_id.name,
        } for template in self.search([]) if template.model in self.env]

    def gallery_preview(self):
        self.ensure_one()
        return {'graph': self.graph or {'nodes': [], 'edges': []},
                'issues': check_graph(self.env, self.model, self.graph)}

    def create_workflow(self, name=None):
        """ A draft workflow from the template, opened in the designer. """
        self.ensure_one()
        self.env['om.workflow'].check_access_rights('create')
        if self.model not in self.env:
            raise UserError(_("The model of this template is not installed."))
        workflow = self.env['om.workflow'].create({
            'name': name or self.name,
            'description': self.description,
            'model_id': self.model_id.id,
            'graph': self.graph,
        })
        return workflow.action_open_designer()

    # ------------------------------------------------------------------
    # files
    # ------------------------------------------------------------------

    def _export_data(self):
        self.ensure_one()
        return {
            'format': FORMAT,
            'version': VERSION,
            'name': self.name,
            'description': self.description or '',
            'model': self.model,
            'graph': export_graph(self.env, self.model, self.graph),
        }

    @api.model
    def _import_data(self, data):
        """ A template from the content of an exported file. """
        if not isinstance(data, dict) or data.get('format') != FORMAT:
            raise UserError(_("This file is not a workflow template."))
        if not isinstance(data.get('version'), int) or data['version'] > VERSION:
            raise UserError(_("This template comes from a newer version of Automation Studio."))
        model = data.get('model')
        if not isinstance(model, str) or model not in self.env:
            raise UserError(_("The template runs on %s, which this database does not have.", model))
        graph = data.get('graph')
        if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list) \
                or not isinstance(graph.get('edges'), list):
            raise UserError(_("The chart of this template is damaged."))
        graph, lost = import_graph(self.env, model, graph)
        return self.create({
            'name': str(data.get('name') or _("Imported Workflow")),
            'description': str(data.get('description') or ''),
            'model_id': self.env['ir.model']._get_id(model),
            'graph': graph,
            'import_note': _("Not found here, to choose again in the designer: %s", ', '.join(lost)) if lost else False,
        })
