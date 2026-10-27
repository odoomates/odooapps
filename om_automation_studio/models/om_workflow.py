import json

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.om_automation_studio.tools import (
    HIDDEN_FIELD_PREFIXES,
    HIDDEN_FIELD_TYPES,
    check_graph,
    eval_domain,
    graph_index,
)

# the units of a date trigger, as Automation Rules know them
AUTOMATION_UNITS = {'minutes': 'minutes', 'hours': 'hour', 'days': 'day', 'weeks': 'day', 'months': 'month'}


def _same_graph(a, b):
    return json.dumps(a or {}, sort_keys=True) == json.dumps(b or {}, sort_keys=True)


class OmWorkflow(models.Model):
    """ A workflow drawn as a flowchart with the designer. The graph being
    drawn is kept on the workflow; publishing it freezes a copy in a new
    version, and each run follows the version it started on, so changing a
    workflow never breaks the runs already waiting. The Start of the published
    version becomes an Automation Rule (or an entry of the Action menu) that
    starts the runs. """
    _name = 'om.workflow'
    _description = 'Workflow'
    _inherit = ['mail.thread']
    _order = 'name, id'

    name = fields.Char(required=True, translate=True, tracking=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=[('transient', '=', False), ('abstract', '=', False)], tracking=True)
    model = fields.Char(related='model_id.model', string='Model Name', store=True, index=True)
    graph = fields.Json(copy=True)
    state = fields.Selection([('draft', 'Draft'), ('active', 'Running'), ('paused', 'Paused')],
                             default='draft', required=True, readonly=True, copy=False, tracking=True)
    version_ids = fields.One2many('om.workflow.version', 'workflow_id', readonly=True)
    version_id = fields.Many2one('om.workflow.version', string='Published Version', readonly=True, copy=False)
    has_changes = fields.Boolean(compute='_compute_has_changes', string='Unpublished Changes')
    trigger_summary = fields.Char(compute='_compute_trigger_summary', string='Starts')
    run_ids = fields.One2many('om.workflow.run', 'workflow_id', readonly=True)
    run_count = fields.Integer(compute='_compute_run_counts')
    active_run_count = fields.Integer(compute='_compute_run_counts', string='Running')
    failed_run_count = fields.Integer(compute='_compute_run_counts', string='Failed')

    automation_id = fields.Many2one('base.automation', readonly=True, copy=False)
    manual_action_id = fields.Many2one('ir.actions.server', readonly=True, copy=False)

    @api.depends('graph', 'version_id.graph')
    def _compute_has_changes(self):
        for workflow in self:
            workflow.has_changes = bool(workflow.version_id) and not _same_graph(workflow.graph,
                                                                               workflow.version_id.graph)

    @api.depends('graph')
    def _compute_trigger_summary(self):
        labels = {
            'create': self.env._("When created"),
            'change': self.env._("When created or updated"),
            'date': self.env._("Based on a date"),
            'manual': self.env._("From the Action menu"),
        }
        for workflow in self:
            start = workflow._start_node(workflow.graph)
            workflow.trigger_summary = labels.get(((start or {}).get('config') or {}).get('trigger'), '')

    def _compute_run_counts(self):
        counts = {}
        for workflow, state, count in self.env['om.workflow.run']._read_group(
                [('workflow_id', 'in', self.ids)], ['workflow_id', 'state'], ['__count']):
            counts.setdefault(workflow.id, {})[state] = count
        for workflow in self:
            by_state = counts.get(workflow.id, {})
            workflow.run_count = sum(by_state.values())
            workflow.active_run_count = by_state.get('running', 0) + by_state.get('waiting', 0)
            workflow.failed_run_count = by_state.get('failed', 0)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('graph'):
                vals['graph'] = self._default_graph()
        return super().create(vals_list)

    def write(self, vals):
        if 'model_id' in vals and self.filtered('version_ids'):
            raise UserError(self.env._("A published workflow keeps its model: duplicate it to use another one."))
        return super().write(vals)

    def unlink(self):
        self._remove_triggers()
        models_left = set(self.search([('id', 'not in', self.ids), ('state', '=', 'active')]).mapped('model'))
        res = super().unlink()
        self._sync_run_bindings(keep_models=models_left)
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        for workflow, vals in zip(self, vals_list):
            vals.setdefault('name', self.env._("%s (copy)", workflow.name))
        return vals_list

    def action_archive(self):
        self.filtered(lambda p: p.state == 'active').action_pause()
        return super().action_archive()

    @api.model
    def _default_graph(self):
        return {
            'nodes': [
                {'id': 'start', 'type': 'start', 'x': 80, 'y': 200, 'label': '',
                 'config': {'trigger': 'create', 'domain': '[]', 'policy': 'single'}},
                {'id': 'end', 'type': 'end', 'x': 560, 'y': 200, 'label': '', 'config': {}},
            ],
            'edges': [{'id': 'e_start', 'source': 'start', 'port': 'out', 'target': 'end'}],
        }

    @api.model
    def _start_node(self, graph):
        return next((node for node in (graph or {}).get('nodes', []) if node.get('type') == 'start'), None)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def action_open_designer(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'om_automation_studio',
            'name': self.name,
            'params': {'workflow_id': self.id},
        }

    def action_view_runs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_automation_studio.om_workflow_run_action')
        action['domain'] = [('workflow_id', '=', self.id)]
        action['context'] = {'search_default_open': 1} if self.active_run_count else {}
        return action

    def action_publish(self):
        """ Freeze the graph in a new version (when it changed) and start
        listening to the trigger of its Start. """
        for workflow in self:
            errors = [issue for issue in check_graph(self.env, workflow.model, workflow.graph)
                      if issue['level'] == 'error']
            if errors:
                raise UserError(self.env._(
                    "Fix the workflow before publishing it:\n%s",
                    "\n".join(f"- {issue['message']}" for issue in errors),
                ))
            if not workflow.version_id or not _same_graph(workflow.graph, workflow.version_id.graph):
                workflow.version_id = self.env['om.workflow.version'].create({
                    'workflow_id': workflow.id,
                    'graph': workflow.graph,
                })
        self.state = 'active'
        # the models whose forms show approvals
        self.env.registry.clear_cache()
        self._sync_triggers()
        self._sync_run_bindings()
        return True

    def action_pause(self):
        """ No new run starts and the waiting runs stay where they are until
        the workflow is published again. """
        self.state = 'paused'
        self.env.registry.clear_cache()
        self._sync_triggers()
        self._sync_run_bindings()
        return True

    # ------------------------------------------------------------------
    # triggers
    # ------------------------------------------------------------------

    def _remove_triggers(self):
        workflows = self.sudo()
        automations = workflows.automation_id
        actions = workflows.manual_action_id | automations.action_server_ids
        workflows.write({'automation_id': False, 'manual_action_id': False})
        actions.unlink()
        automations.unlink()

    def _sync_triggers(self):
        """ Make the Automation Rule or Action menu entry that starts the runs
        match the Start of the published version. """
        self._remove_triggers()
        for workflow in self.sudo().filtered(lambda p: p.state == 'active' and p.version_id):
            start = workflow._start_node(workflow.version_id.graph) or {}
            config = start.get('config') or {}
            trigger = config.get('trigger')
            action_vals = {
                'name': self.env._("Start workflow %s", workflow.name),
                'model_id': workflow.model_id.id,
                'state': 'om_workflow',
                'om_workflow_id': workflow.id,
            }
            if trigger == 'manual':
                workflow.manual_action_id = self.env['ir.actions.server'].create({
                    **action_vals,
                    'binding_model_id': workflow.model_id.id,
                    'binding_view_types': 'list,form',
                })
                continue
            vals = workflow._automation_vals(config)
            automation = self.env['base.automation'].create(vals)
            self.env['ir.actions.server'].create({
                **action_vals,
                'usage': 'base_automation',
                'base_automation_id': automation.id,
            })
            workflow.automation_id = automation

    def _automation_vals(self, config):
        """ The Automation Rule for the Start ``config`` of the workflow. """
        self.ensure_one()
        trigger = config.get('trigger')
        domain = eval_domain(self.env, config.get('domain'))
        vals = {
            'name': self.env._("Workflow: %s", self.name),
            'model_id': self.model_id.id,
            'filter_domain': repr(domain) if domain else False,
        }
        if trigger == 'create':
            vals['trigger'] = 'on_create'
        elif trigger == 'change':
            field_names = config.get('fields') or []
            vals.update({
                'trigger': 'on_create_or_write',
                'trigger_field_ids': [Command.set(self.env['ir.model.fields'].search([
                    ('model', '=', self.model), ('name', 'in', field_names)]).ids)],
            })
            # only the records the condition was not true for before the change
            if domain and config.get('becomes', True):
                vals['filter_pre_domain'] = repr(list(~Domain(domain)))
        elif trigger == 'date':
            unit = config.get('unit') or 'days'
            amount = int(config.get('amount') or 0) * (7 if unit == 'weeks' else 1)
            vals.update({
                'trigger': 'on_time',
                'trg_date_id': self.env['ir.model.fields']._get(self.model, config['date_field']).id,
                'trg_date_range': amount,
                'trg_date_range_type': AUTOMATION_UNITS.get(unit, 'day'),
                'trg_date_range_mode': config.get('direction') or 'after',
            })
        return vals

    @api.model
    def _sync_run_bindings(self, keep_models=None):
        """ One "Workflow Runs" entry in the Action menu of each model a
        running workflow works on. """
        if keep_models is None:
            keep_models = set(self.sudo().search([('state', '=', 'active')]).mapped('model'))
        Window = self.env['ir.actions.act_window'].sudo()
        bindings = Window.search([('res_model', '=', 'om.workflow.run'), ('binding_model_id', '!=', False),
                                  ('context', 'like', 'om_workflow_binding')])
        bound = {binding.binding_model_id.model: binding for binding in bindings}
        for model in set(bound) - set(keep_models):
            bound[model].unlink()
        group = self.env.ref('om_automation_studio.om_automation_studio_group_supervisor')
        Window.create([{
            'name': self.env._("Workflow Runs"),
            'res_model': 'om.workflow.run',
            'binding_model_id': self.env['ir.model']._get_id(model),
            'binding_view_types': 'form',
            'view_mode': 'list,form',
            'domain': "[('res_model', '=', active_model), ('res_id', '=', active_id)]",
            'context': "{'om_workflow_binding': True}",
            'group_ids': [Command.link(group.id)],
        } for model in set(keep_models) - set(bound)])

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------

    def _start_runs(self, records):
        """ Start a run of the published version on each of ``records``,
        unless the run policy of the Start says otherwise. """
        self.ensure_one()
        Run = self.env['om.workflow.run'].sudo()
        if self.state != 'active' or not self.version_id or not records:
            return Run
        # a workflow that starts itself through the records it changes stops there
        depth = self.env.context.get('om_workflow_depth', 0)
        if depth >= 3:
            return Run
        config = (self._start_node(self.version_id.graph) or {}).get('config') or {}
        policy = config.get('policy') or 'single'
        records = records.exists()
        if policy != 'multiple':
            domain = [('workflow_id', '=', self.id), ('res_id', 'in', records.ids)]
            if policy == 'single':
                domain.append(('state', 'in', ('running', 'waiting')))
            busy = set(Run.search(domain).mapped('res_id'))
            records = records.filtered(lambda r: r.id not in busy)
        if not records:
            return Run
        runs = Run.create([{
            'workflow_id': self.id,
            'version_id': self.version_id.id,
            'res_model': self.model,
            'res_id': record.id,
            'res_name': record.display_name,
        } for record in records])
        runs.with_context(om_workflow_depth=depth + 1)._advance()
        return runs

    # ------------------------------------------------------------------
    # designer
    # ------------------------------------------------------------------

    def designer_load(self):
        self.ensure_one()
        return {
            'workflow': self._designer_info(),
            'graph': self.graph or self._default_graph(),
            'fields': self.designer_fields(self.model),
            'issues': check_graph(self.env, self.model, self.graph),
        }

    def _designer_info(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'model': self.model,
            'model_name': self.model_id.name,
            'state': self.state,
            'has_changes': self.has_changes,
            'version': self.version_id.number,
            'has_activities': 'activity_ids' in self.env[self.model]._fields,
            'has_chatter': 'message_ids' in self.env[self.model]._fields,
        }

    def designer_save(self, graph, name=None):
        self.ensure_one()
        vals = {'graph': graph}
        if name:
            vals['name'] = name
        self.write(vals)
        return {'workflow': self._designer_info(), 'issues': check_graph(self.env, self.model, graph)}

    def designer_publish(self, graph, name=None):
        self.designer_save(graph, name)
        self.action_publish()
        return {'workflow': self._designer_info(), 'issues': check_graph(self.env, self.model, graph)}

    def designer_pause(self):
        self.action_pause()
        return {'workflow': self._designer_info()}

    @api.model
    def designer_fields(self, model):
        """ The fields of ``model`` the designer offers, by label. """
        if not model or model not in self.env:
            return []
        self.env['om.workflow'].check_access('write')
        Model = self.env[model]
        result = []
        for name, field in Model._fields.items():
            if name.startswith(HIDDEN_FIELD_PREFIXES) or field.type in HIDDEN_FIELD_TYPES:
                continue
            if field.groups and not self.env.user.has_groups(field.groups):
                continue
            result.append({
                'name': name,
                'string': field._description_string(self.env),
                'type': field.type,
                'relation': getattr(field, 'comodel_name', None) or False,
                'selection': (field._description_selection(self.env)
                              if field.type == 'selection' else False),
                'settable': not (field.compute and not field.inverse and field.readonly),
                'store': bool(field.store),
                'required': bool(field.required),
            })
        return sorted(result, key=lambda f: f['string'].lower())

    @api.model
    def designer_model_name(self, model_id):
        model = self.env['ir.model'].browse(model_id).exists()
        return model.model if model else False

    def designer_run(self, run_id):
        """ What the run viewer shows: the version the run follows and the
        steps it went through. """
        self.ensure_one()
        run = self.env['om.workflow.run'].browse(run_id)
        run.check_access('read')
        nodes, __ = graph_index(run.version_id.graph)
        return {
            'workflow': {**self._designer_info(), 'version': run.version_id.number},
            'graph': run.version_id.graph,
            'run': {
                'id': run.id,
                'state': run.state,
                'record': run.res_name,
                'node': run.node_key,
                'wake_at': run.wake_at,
                'error': run.error or '',
            },
            'steps': [{
                'node': step.node_key,
                'port': step.port or '',
                'state': step.state,
                'date': step.date_start,
                'message': step.message or '',
                'label': step.node_label or (nodes.get(step.node_key) or {}).get('label') or '',
            } for step in run.step_ids.sorted('id')],
        }
