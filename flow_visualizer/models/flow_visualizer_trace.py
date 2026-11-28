# One traced click: what it created, edited and deleted, as a tree. The last
# few of each user are kept.
import logging

from odoo import SUPERUSER_ID, api, fields, models

from . import simulation

_logger = logging.getLogger(__name__)

TRACES_KEPT = 60


class FlowVisualizerTrace(models.Model):
    _name = 'flow.visualizer.trace'
    _description = 'Flow Visualizer Trace'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    name = fields.Char(required=True)
    model = fields.Char()
    method = fields.Char()
    res_ids = fields.Json()
    state = fields.Selection([('done', 'Done'), ('failed', 'Failed')], required=True, default='done')
    error = fields.Text()
    duration = fields.Float(string='Duration (ms)')
    query_count = fields.Integer()
    record_count = fields.Integer()
    truncated = fields.Boolean()
    tree = fields.Json()
    story = fields.Json()

    @api.model
    def _flow_cursor(self, registry):
        """ A cursor of its own for the traces. During a simulation, out of
        it: the traces of the steps stay when one goes back in time. """
        if simulation.current(registry.db_name):
            return simulation.real_cursor(registry.db_name)
        return registry.cursor()

    @api.model
    def _flow_save(self, registry, values):
        """ Write a trace on a cursor of its own, keeping the user's last ones. """
        try:
            with self._flow_cursor(registry) as cr:
                Trace = api.Environment(cr, SUPERUSER_ID, {})[self._name]
                trace = Trace.create(values)
                Trace.search([('user_id', '=', values['user_id'])], offset=TRACES_KEPT).unlink()
                return trace.id
        except Exception:  # noqa: BLE001 - a lost trace never breaks the traced call
            _logger.warning("Could not save the trace of %s", values.get('name'), exc_info=True)
            return None

    def _flow_data(self):
        return [{
            'id': trace.id,
            'name': trace.name,
            'model': trace.model,
            'method': trace.method,
            'res_ids': trace.res_ids or [],
            'state': trace.state,
            'error': trace.error or '',
            'duration': round(trace.duration),
            'query_count': trace.query_count,
            'record_count': trace.record_count,
            'truncated': trace.truncated,
            'date': fields.Datetime.to_string(trace.create_date),
            'tree': trace.tree or [],
            'story': trace.story,
        } for trace in self]
