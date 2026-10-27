import datetime as dt
import logging

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools.misc import format_datetime

from odoo.addons.om_automation_studio.tools import eval_domain, graph_index, offset

_logger = logging.getLogger(__name__)

# steps one run goes through at once before it is stopped as a runaway loop
MAX_STEPS = 100
# runs the cron continues per commit: each step is a savepoint, keep it small
CRON_BATCH = 20


class OmWorkflowRun(models.Model):
    """ One record going through a workflow: the step it is on, whether it
    waits there, and the steps it went through. A run follows the version
    of the workflow it started on. """
    _name = 'om.workflow.run'
    _description = 'Workflow Run'
    _order = 'id desc'

    workflow_id = fields.Many2one('om.workflow', required=True, ondelete='cascade', index=True, readonly=True)
    version_id = fields.Many2one('om.workflow.version', required=True, ondelete='restrict', readonly=True)
    version = fields.Integer(related='version_id.number')
    res_model = fields.Char('Model Name', required=True, readonly=True, index=True)
    res_id = fields.Many2oneReference('Record ID', model_field='res_model', required=True, readonly=True,
                                      index=True)
    res_name = fields.Char('Record', readonly=True)
    state = fields.Selection([
        ('running', 'Running'),
        ('waiting', 'Waiting'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='running', required=True, readonly=True, index=True)
    node_key = fields.Char('Step Key', readonly=True)
    node_label = fields.Char('Current Step', compute='_compute_node_label')
    wake_at = fields.Datetime('Continues On', readonly=True, index='btree_not_null')
    # the type of the step the run waits on: a Wait Until is checked by
    # every round of the cron, the others when their time comes
    wait_type = fields.Char(readonly=True)
    end_date = fields.Datetime('Ended On', readonly=True)
    error = fields.Text(readonly=True)
    step_ids = fields.One2many('om.workflow.run.step', 'run_id', string='Steps', readonly=True)
    approval_ids = fields.One2many('om.workflow.approval', 'run_id', readonly=True)

    @api.depends('node_key', 'version_id.graph')
    def _compute_node_label(self):
        for run in self:
            nodes, __ = graph_index(run.version_id.graph)
            node = nodes.get(run.node_key)
            run.node_label = self.env['om.workflow.run.step']._label(node) if node else ''

    @api.depends('res_name', 'workflow_id')
    def _compute_display_name(self):
        for run in self:
            run.display_name = f"{run.workflow_id.name}: {run.res_name or ''}"

    @api.model_create_multi
    def create(self, vals_list):
        runs = super().create(vals_list)
        for run in runs:
            if not run.node_key:
                start = self.env['om.workflow']._start_node(run.version_id.graph)
                run.node_key = start and start['id']
        return runs

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------

    def action_open_record(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'views': [(False, 'form')],
        }

    def action_view_path(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'om_automation_studio',
            'name': self.display_name,
            'params': {'workflow_id': self.workflow_id.id, 'run_id': self.id},
        }

    def action_cancel(self):
        self._check_supervisor()
        runs = self.filtered(lambda r: r.state in ('running', 'waiting', 'failed'))
        runs._stop('cancelled', self.env._("Cancelled by %s.", self.env.user.name))
        return True

    def action_retry(self):
        """ Run the failed step again, then go on from there. """
        self._check_supervisor()
        runs = self.filtered(lambda r: r.state == 'failed')
        runs.sudo().write({'state': 'running', 'error': False, 'end_date': False})
        runs.sudo()._advance()
        return True

    def _check_supervisor(self):
        if not self.env.user.has_group('om_automation_studio.om_automation_studio_group_supervisor'):
            raise UserError(self.env._("Only workflow supervisors can change runs."))

    # ------------------------------------------------------------------
    # engine
    # ------------------------------------------------------------------

    def _record(self):
        self.ensure_one()
        if self.res_model not in self.env:
            return None
        record = self.env[self.res_model].sudo().browse(self.res_id).exists()
        return record.with_context(mail_notify_force_send=False) if record else None

    def _stop_domain(self):
        start = self.env['om.workflow']._start_node(self.version_id.graph) or {}
        return eval_domain(self.env, (start.get('config') or {}).get('stop_domain'))

    def _advance(self):
        """ Go through the steps of each run until it waits or ends. """
        for run in self:
            run._advance_one()

    def _advance_one(self):
        self.ensure_one()
        Step = self.env['om.workflow.run.step'].sudo()
        nodes, edges = graph_index(self.version_id.graph)
        stop_domain = self._stop_domain()
        count = 0
        while self.state == 'running':
            record = self._record()
            if record is None:
                self._stop('failed', self.env._("The record no longer exists."))
                return
            if stop_domain and record.filtered_domain(stop_domain):
                self._stop('done', self.env._("Stopped: the stop condition is met."))
                return
            node = nodes.get(self.node_key)
            if not node:
                self._stop('failed', self.env._("The step of the run no longer exists."))
                return
            count += 1
            if count > MAX_STEPS:
                self._stop('failed', self.env._("Stopped after %s steps in a row: check the loops.", MAX_STEPS))
                return
            step = Step.create({'run_id': self.id, 'node_key': node['id'], 'node_label': Step._label(node),
                                'node_type': node['type']})
            if node['type'] == 'end':
                step._close('done')
                self._stop('done')
                return
            try:
                # a step that fails leaves no trace and does not undo what
                # triggered the run: the run stops on it, to be retried
                with self.env.cr.savepoint():
                    outcome = getattr(self, f"_node_{node['type']}")(node, record, step)
            except Exception as error:  # noqa: BLE001 any error of any step, logged on the run
                _logger.info("Workflow run %s failed on step %s", self.id, node['id'], exc_info=True)
                message = str(error.args[0] if isinstance(error, UserError) and error.args else error)
                step._close('failed', message=message)
                self._stop('failed', message)
                return
            if isinstance(outcome, tuple):
                self.write({'state': 'waiting', 'wake_at': outcome[1], 'wait_type': node['type']})
                step.state = 'waiting'
                if outcome[1]:
                    self.env.ref('om_automation_studio.ir_cron_wake_runs')._trigger(at=outcome[1])
                return
            self._leave(node, step, outcome, edges)

    def _leave(self, node, step, port, edges):
        """ Close ``step`` by ``port`` and move to the step the arrow leads to. """
        step._close('done', port=port)
        target = edges.get((node['id'], port))
        if not target:
            self._stop('done')
            return
        self.write({'node_key': target, 'state': 'running', 'wake_at': False, 'wait_type': False})

    def _resume(self, port, message=None):
        """ Leave the step the run waits on by ``port``. """
        for run in self.filtered(lambda r: r.state == 'waiting'):
            nodes, edges = graph_index(run.version_id.graph)
            node = nodes.get(run.node_key)
            step = run.step_ids.filtered(lambda s: s.state == 'waiting')[:1]
            if message:
                step.message = message
            if not node:
                run._stop('failed', self.env._("The step of the run no longer exists."))
                continue
            run._leave(node, step, port, edges)
            run._advance_one()

    def _stop(self, state, message=None):
        runs = self.sudo()
        vals = {'state': state, 'wake_at': False, 'wait_type': False}
        if state != 'failed':
            vals['end_date'] = fields.Datetime.now()
        if message and state == 'failed':
            vals['error'] = message
        runs.write(vals)
        runs.step_ids.filtered(lambda s: s.state == 'waiting')._close(
            'cancelled' if state == 'cancelled' else 'done', message=message)
        runs.approval_ids.filtered(lambda a: a.state == 'pending')._close('cancelled')

    @api.model
    def _cron_wake(self):
        """ Continue the waiting runs whose time has come, check the
        conditions the others wait for. """
        now = fields.Datetime.now()
        runs = self._due_runs(now)
        Cron = self.env['ir.cron']
        Cron._commit_progress(remaining=len(runs))
        for start in range(0, len(runs), CRON_BATCH):
            batch = runs[start:start + CRON_BATCH]
            batch._wake(now)
            if not Cron._commit_progress(len(batch)):
                break

    @api.model
    def _due_runs(self, now):
        return self.search(Domain('state', '=', 'waiting') & Domain('workflow_id.state', '=', 'active')
                           & (Domain('wake_at', '<=', now) | Domain('wait_type', 'in', ('wait_until', 'approval'))),
                           order='wake_at, id')

    def _wake(self, now):
        for run in self:
            if run.state != 'waiting':
                continue
            try:
                with self.env.cr.savepoint():
                    run._wake_one(now)
            except Exception as error:  # noqa: BLE001 one broken run must not stop the others
                _logger.info("Workflow run %s could not continue", run.id, exc_info=True)
                run._stop('failed', str(error))

    def _wake_one(self, now):
        self.ensure_one()
        nodes, __ = graph_index(self.version_id.graph)
        node = nodes.get(self.node_key) or {}
        config = node.get('config') or {}
        record = self._record()
        if record is None:
            self._stop('failed', self.env._("The record no longer exists."))
            return
        stop_domain = self._stop_domain()
        if stop_domain and record.filtered_domain(stop_domain):
            self._stop('done', self.env._("Stopped: the stop condition is met."))
            return
        due = self.wake_at and self.wake_at <= now
        if node.get('type') == 'wait':
            if due:
                self._resume('out')
        elif node.get('type') == 'wait_until':
            if record.filtered_domain(eval_domain(self.env, config.get('domain'))):
                self._resume('done')
            elif due:
                self._resume('timeout', self.env._("Time limit reached."))
        elif node.get('type') == 'approval' and due:
            self.approval_ids.filtered(lambda a: a.state == 'pending')._close('expired')
            self._resume('timeout', self.env._("No answer in time."))

    # ------------------------------------------------------------------
    # steps
    # ------------------------------------------------------------------

    def _node_start(self, node, record, step):
        return 'out'

    def _node_condition(self, node, record, step):
        domain = eval_domain(self.env, node['config'].get('domain'))
        return 'yes' if record.filtered_domain(domain) else 'no'

    def _node_wait(self, node, record, step):
        config = node['config']
        now = fields.Datetime.now()
        if config.get('mode') == 'date':
            base = record[config['date_field']]
            if not base:
                step.message = self.env._("No date to wait for: went on at once.")
                return 'out'
            if not isinstance(base, dt.datetime):
                base = dt.datetime.combine(base, dt.time.min)
            delta = offset(config.get('amount'), config.get('unit'))
            wake_at = base - delta if config.get('direction') == 'before' else base + delta
        else:
            wake_at = now + offset(config.get('amount'), config.get('unit'))
        if wake_at <= now:
            return 'out'
        step.message = self.env._("Until %s", format_datetime(self.env, wake_at))
        return ('wait', wake_at)

    def _node_wait_until(self, node, record, step):
        config = node['config']
        if record.filtered_domain(eval_domain(self.env, config.get('domain'))):
            return 'done'
        deadline = False
        if config.get('timeout'):
            deadline = fields.Datetime.now() + offset(config.get('amount'), config.get('unit'))
        return ('wait', deadline)

    def _node_approval(self, node, record, step):
        config = node['config']
        user = self._step_user(config, record)
        if not user:
            raise UserError(self.env._("There is no approver: the field for it is empty."))
        title = self._render(config.get('title') or self.env._("Approve {{ object.display_name }}"), record)
        approval = self.env['om.workflow.approval'].sudo().create({
            'name': title,
            'run_id': self.id,
            'node_key': node['id'],
            'user_id': user.id,
            'note': self._render(config.get('note') or '', record),
            'lock': config.get('lock', True),
            'lock_fields': self._lock_fields(config, record),
            'approver_only': config.get('approver_only', False),
        })
        approval._post_asked(record)
        step.message = self.env._("Asked %s", user.name)
        deadline = False
        if config.get('timeout'):
            deadline = fields.Datetime.now() + offset(config.get('amount'), config.get('unit'))
            approval.deadline = deadline
        return ('wait', deadline)

    def _lock_fields(self, config, record):
        """ The fields an Approval step blocks: the chosen ones (by default
        the status), or every field (None). """
        if not config.get('lock', True) or config.get('lock_mode') == 'all':
            return None
        return config.get('lock_fields') or (['state'] if 'state' in record._fields else None)

    def _node_update(self, node, record, step):
        record.write(self._values(record, record, node['config'].get('values')))
        return 'out'

    def _node_create(self, node, record, step):
        config = node['config']
        Target = self.env[config['model']].sudo()
        vals = self._values(Target, record, config.get('values'))
        if config.get('link_field'):
            vals[config['link_field']] = record.id
        created = Target.create(vals)
        step.message = self.env._("Created %s", created.display_name)
        return 'out'

    def _node_email(self, node, record, step):
        template = self.env['mail.template'].sudo().browse(node['config']['template_id']).exists()
        if not template:
            raise UserError(self.env._("The email template no longer exists."))
        if 'message_ids' in record._fields:
            record.with_context(mail_post_autofollow_author_skip=True).message_post_with_source(
                template, message_type='auto_comment', subtype_xmlid='mail.mt_comment')
        else:
            template.send_mail(record.id, force_send=False)
        return 'out'

    def _node_activity(self, node, record, step):
        config = node['config']
        user = self._step_user(config, record) or self.env.user
        record.activity_schedule(
            activity_type_id=config['activity_type_id'],
            summary=self._render(config.get('summary') or '', record),
            note=self._render(config.get('note') or '', record),
            date_deadline=fields.Date.context_today(self) + offset(config.get('days'), 'days'),
            user_id=user.id,
        )
        step.message = self.env._("For %s", user.name)
        return 'out'

    def _node_note(self, node, record, step):
        config = node['config']
        body = self._render(config.get('body') or '', record)
        if config.get('message'):
            record.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_comment')
        else:
            record.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')
        return 'out'

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _step_user(self, config, record):
        if config.get('assign', 'user') == 'field':
            return record[config['user_field']]
        return self.env['res.users'].sudo().browse(config.get('user_id')).exists()

    def _render(self, text, record):
        """ ``text`` with its ``{{ object.field }}`` placeholders filled from ``record``. """
        if '{{' not in text:
            return text
        return self.env['mail.render.mixin'].sudo()._render_template(
            text, record._name, record.ids, engine='inline_template')[record.id]

    def _values(self, Target, source, rows):
        """ The values to write on a record of ``Target`` for the field rows
        of an Update or Create step, ``source`` being the record of the run. """
        vals = {}
        for row in rows or []:
            field = Target._fields[row['field']]
            mode = row.get('mode', 'value')
            if mode == 'clear':
                value = [Command.clear()] if field.type == 'many2many' else False
            elif mode == 'today':
                delta = offset(row.get('offset'), 'days')
                value = (fields.Datetime.now() + delta if field.type == 'datetime'
                         else fields.Date.context_today(self) + delta)
            elif mode == 'field':
                value = source[row['source']]
                if field.type == 'many2one':
                    value = value.id
                elif field.type == 'many2many':
                    value = [Command.set(value.ids)]
                elif isinstance(value, models.BaseModel):
                    value = value.display_name
            else:
                value = row.get('value')
                if field.type == 'many2many':
                    value = [Command.link(res_id) for res_id in value or []]
                elif field.type in ('integer', 'many2one'):
                    value = int(value or 0) or (0 if field.type == 'integer' else False)
                elif field.type in ('float', 'monetary'):
                    value = float(value or 0)
                elif field.type == 'boolean':
                    value = bool(value)
                elif field.type == 'datetime' and value:
                    # the designer gives the "2026-10-27T09:30" of a datetime-local input
                    value = fields.Datetime.to_datetime(value.replace('T', ' ')[:19])
                elif field.type in ('date', 'selection') and not value:
                    value = False
            vals[field.name] = value
        return vals
