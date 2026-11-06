# The calls the web client makes are traced while the visualizer is on for the
# session, and the traces are read back by its panel.
from odoo import SUPERUSER_ID, api, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.web.controllers.dataset import DataSet

from ..models import simulation
from ..models.code_link import open_code
from ..models.ir_http import SESSION_KEY
from ..models.tracer import CURRENT, Tracer

# the calls that only read: never traced
UNTRACED = frozenset({
    'read', 'web_read', 'search', 'search_read', 'web_search_read', 'search_count', 'search_fetch',
    'name_search', 'web_name_search', 'read_group', 'web_read_group', 'formatted_read_group',
    'fields_get', 'get_views', 'onchange', 'default_get', 'has_access', 'check_access',
    'read_progress_bar', 'search_panel_select_range', 'search_panel_select_multi_range',
    'get_formview_id', 'get_formview_action', 'get_empty_list_help', 'web_read_unique',
})


def traced(model, method, args, call):
    running = simulation.current(request.db)
    if method in UNTRACED or not (request.session.get(SESSION_KEY) or running):
        return call()
    tracer = Tracer(request.env, model, method, args)
    token = CURRENT.set(tracer)
    error = None
    try:
        return call()
    except Exception as exc:
        error = exc
        raise
    finally:
        CURRENT.reset(token)
        flush_error = tracer.finish(request.env, error)
        if flush_error is not None:
            raise flush_error
        # in a simulation, a click that changed data is a step one can go back to
        if running and tracer.trace_id and tracer.count and not tracer.failed and is_step(model, method):
            running.ask('step', trace_id=tracer.trace_id, name=f'{model}.{method}', model=model,
                        res_id=tracer.res_ids[0] if tracer.res_ids else False, **step_label(tracer))


def is_step(model, method):
    """ Filling a wizard is not a step: the button that runs it is. """
    Model = request.env[model] if model in request.env else None
    return not (Model is not None and Model._transient and method in ('create', 'write', 'web_save'))


def step_label(tracer):
    """ "Confirm" and "S00043": the step as a person tells it. """
    story = tracer.story or {}
    action = story.get('action') or tracer.method
    documents = story.get('documents') or []
    target = next((card for card in documents if card['kind'] == 'clicked'), None) \
        or next((card for card in documents if card['kind'] == 'create'), None) \
        or (documents[0] if documents else None)
    Model = request.env[tracer.model] if tracer.model in request.env else None
    return {
        'action': action,
        'target': target['name'] if target else (Model._description if Model is not None else ''),
        'target_model': target['model'] if target else tracer.model,
        'target_id': target['id'] if target and target.get('exists') else False,
    }


class DataSetFlow(DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        return traced(model, method, args, lambda: super(DataSetFlow, self).call_kw(
            model, method, args, kwargs, path=path))

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        return traced(model, method, args, lambda: super(DataSetFlow, self).call_button(
            model, method, args, kwargs, path=path))


class FlowVisualizer(http.Controller):

    def _check(self):
        if not request.env.user.has_group('base.group_system'):
            raise AccessError(request.env._("Only administrators can trace what a click does."))

    @http.route('/flow_visualizer/toggle', type='jsonrpc', auth='user')
    def toggle(self, enabled):
        self._check()
        request.session[SESSION_KEY] = bool(enabled)
        return bool(enabled)

    def _trace_env(self):
        """ The traces live out of any simulation: read them there. """
        if simulation.current(request.db):
            cr = simulation.real_cursor(request.db)
            return cr, api.Environment(cr, SUPERUSER_ID, {})
        return None, request.env(su=True)

    @http.route('/flow_visualizer/traces', type='jsonrpc', auth='user', readonly=True)
    def traces(self, after_id=0, limit=20):
        self._check()
        cr, env = self._trace_env()
        try:
            traces = env['flow.visualizer.trace'].search(
                [('user_id', '=', request.env.uid), ('id', '>', after_id)], limit=limit)
            return traces._flow_data()
        finally:
            if cr:
                cr.close()

    @http.route('/flow_visualizer/clear', type='jsonrpc', auth='user')
    def clear(self):
        self._check()
        cr, env = self._trace_env()
        try:
            env['flow.visualizer.trace'].search([('user_id', '=', request.env.uid)]).unlink()
            if cr:
                cr.commit()
        finally:
            if cr:
                cr.close()
        return True

    @http.route('/flow_visualizer/rewind/plan', type='jsonrpc', auth='user', readonly=True)
    def rewind_plan(self, model, res_id, target):
        if not request.env.user._is_internal():
            raise AccessError(request.env._("Only internal users can go back on documents."))
        return request.env['flow.visualizer.record'].rewind_plan(model, res_id, target)

    @http.route('/flow_visualizer/rewind/apply', type='jsonrpc', auth='user')
    def rewind_apply(self, model, res_id, target):
        if not request.env.user._is_internal():
            raise AccessError(request.env._("Only internal users can go back on documents."))
        # traced like a click: in a simulation, one more step to go back on
        return traced('flow.visualizer.record', 'rewind_apply', [[res_id]], lambda: request.env[
            'flow.visualizer.record'].rewind_apply(model, res_id, target))

    #
    # the simulator
    #

    def _simulation(self):
        self._check()
        running = simulation.current(request.db)
        if not running:
            raise UserError(request.env._("No simulation runs on this database."))
        return running

    @http.route('/flow_visualizer/sim/state', type='jsonrpc', auth='user', readonly=True)
    def sim_state(self):
        self._check()
        running = simulation.current(request.db)
        return running.state() if running else {'active': False, 'steps': []}

    @http.route('/flow_visualizer/sim/start', type='jsonrpc', auth='user')
    def sim_start(self):
        self._check()
        try:
            running = simulation.start(request.db, request.env.uid)
        except simulation.SimulationError as exc:
            raise UserError(str(exc)) from exc
        return running.state()

    @http.route('/flow_visualizer/sim/rewind', type='jsonrpc', auth='user')
    def sim_rewind(self, step_id=0):
        running = self._simulation()
        if step_id and not any(step['id'] == step_id and not step['abandoned'] for step in running.steps):
            raise UserError(request.env._("This step cannot be gone back to anymore."))
        running.ask('rewind', step_id=step_id)
        return True

    @http.route('/flow_visualizer/sim/keep', type='jsonrpc', auth='user')
    def sim_keep(self):
        self._simulation().ask('keep')
        return True

    @http.route('/flow_visualizer/sim/discard', type='jsonrpc', auth='user')
    def sim_discard(self):
        self._simulation().ask('discard')
        return True

    @http.route('/flow_visualizer/record', type='jsonrpc', auth='user', readonly=True)
    def record(self, model, res_id):
        if not request.env.user._is_internal():
            raise AccessError(request.env._("Only internal users can see the flow of a record."))
        return request.env['flow.visualizer.record'].flow_of(model, res_id)

    @http.route('/flow_visualizer/open_code', type='jsonrpc', auth='user', readonly=True)
    def open_code(self, file, line):
        self._check()
        return open_code(file, line, request.httprequest.remote_addr)
