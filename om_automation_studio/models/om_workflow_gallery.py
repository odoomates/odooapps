from odoo import api, models
from odoo.exceptions import UserError

from odoo.addons.om_automation_studio.tools import PATTERNS, PRESETS, check_graph
from odoo.addons.om_automation_studio.tools.templates import (
    clean,
    missing,
    preset_values,
)


class OmWorkflow(models.Model):
    _inherit = 'om.workflow'

    # ------------------------------------------------------------------
    # the template dialog
    # ------------------------------------------------------------------

    @api.model
    def template_list(self):
        self.check_access('create')
        return [{
            'key': pattern.key,
            'name': pattern.name(self.env),
            'description': pattern.description(self.env),
            'icon': pattern.icon,
        } for pattern in PATTERNS.values()]

    @api.model
    def template_models(self, key):
        """ The models ``key`` can run on, those with a preset first. """
        self.check_access('create')
        pattern = self._pattern(key)
        presets = {model for (preset_key, model) in PRESETS if preset_key == key}
        result = [{'model': model.model, 'name': model.name, 'preset': model.model in presets}
                  for model in self._template_models() if pattern.fits(self.env, self.env[model.model])]
        return sorted(result, key=lambda item: (not item['preset'], item['name'].lower()))

    @api.model
    def template_setup(self, key, model):
        """ The slots of ``key`` on ``model``, filled with the guesses and
        the preset. """
        self.check_access('create')
        pattern, Model = self._pattern(key), self._template_model(model)
        slots = pattern.slots(self.env, Model)
        values = clean(self.env, slots, preset_values(self.env, key, model))
        return {'slots': slots, 'values': values, 'name': self._template_name(key, model)}

    @api.model
    def template_preview(self, key, model, values):
        """ The chart ``key`` draws on ``model`` with ``values``, and what keeps
        it from running. """
        self.check_access('create')
        graph, todo = self._template_graph(key, model, values)
        if not graph:
            return {'graph': False, 'missing': todo, 'issues': []}
        return {'graph': graph, 'missing': [], 'issues': check_graph(self.env, model, graph)}

    @api.model
    def template_create(self, key, model, values, name=None):
        """ A draft workflow from ``key``, opened in the designer. """
        self.check_access('create')
        workflow = self._template_create(key, model, values, name)
        return workflow.action_open_designer()

    def action_save_as_template(self):
        """ Keep the chart as a template, to start other workflows from. """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Save as Template"),
            'res_model': 'om.workflow.template',
            'views': [(self.env.ref('om_automation_studio.om_workflow_template_view_form_save').id, 'form')],
            'target': 'new',
            'context': {
                'default_name': self.name,
                'default_description': self.description,
                'default_model_id': self.model_id.id,
                'default_graph': self.graph,
            },
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _pattern(self, key):
        if key not in PATTERNS:
            raise UserError(self.env._("This template does not exist."))
        return PATTERNS[key]

    def _template_models(self):
        """ The models a template may run on: with a chatter and activities. """
        models = self.env['ir.model'].sudo().search([('transient', '=', False)])
        return models.filtered(lambda model: (
            model.model in self.env
            and not self.env[model.model]._abstract
            and not model.model.startswith('om.workflow')
            and {'message_ids', 'activity_ids'} <= set(self.env[model.model]._fields)
            and self.env[model.model].has_access('read')
        ))

    def _template_model(self, model):
        if model not in self._template_models().mapped('model'):
            raise UserError(self.env._("Workflows cannot run on this model."))
        return self.env[model]

    def _template_name(self, key, model):
        preset = PRESETS.get((key, model))
        if preset:
            return preset[1]
        return self.env._("%(template)s: %(model)s", template=PATTERNS[key].name(self.env),
                          model=self.env['ir.model']._get(model).name)

    def _template_graph(self, key, model, values):
        """ The chart of ``key`` on ``model``, or what is missing for it. """
        pattern, Model = self._pattern(key), self._template_model(model)
        slots = pattern.slots(self.env, Model)
        values = clean(self.env, slots, values or {})
        todo = missing(slots, values)
        if todo:
            return False, todo
        return pattern.build(self.env, Model, values), []

    def _template_create(self, key, model, values, name=None):
        graph, todo = self._template_graph(key, model, values)
        if todo:
            raise UserError(self.env._("Fill in: %s", ', '.join(todo)))
        return self.create({
            'name': name or self._template_name(key, model),
            'description': PATTERNS[key].description(self.env),
            'model_id': self.env['ir.model']._get_id(model),
            'graph': graph,
        })
