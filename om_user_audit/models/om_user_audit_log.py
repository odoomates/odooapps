# One line per event. Lines are kept on the transaction and written once, just
# before it commits: a rolled back change leaves no line. The events that must
# survive a rollback (a failed sign-in, a refusal) are written on a cursor of
# their own.
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.http import request
from odoo.modules import module

from .client_call import RPC_ADDRESS

_logger = logging.getLogger(__name__)

EVENTS = [
    ('login', 'Sign-in'),
    ('login_failed', 'Failed Sign-in'),
    ('logout', 'Sign-out'),
    ('session_end', 'Session Ended'),
    ('read', 'Read'),
    ('create', 'Create'),
    ('write', 'Edit'),
    ('unlink', 'Delete'),
    ('export', 'Export'),
    ('import', 'Import'),
    ('print', 'Print'),
    ('refused', 'Refused'),
    ('other', 'Other'),
]
BUFFER_KEY = 'om_user_audit_lines'
RECORD_IDS_KEPT = 20


def request_context():
    """ The address and the browser of the current request. """
    if not request:
        address = RPC_ADDRESS.get()
        return {'ip': address} if address else {}
    httprequest = request.httprequest
    values = {'ip': httprequest.remote_addr or False}
    agent = httprequest.user_agent
    if agent and agent.string:
        values['user_agent'] = agent.string[:500]
    return values


class OmUserAuditLog(models.Model):
    _name = 'om.user.audit.log'
    _description = 'User Audit Log'
    _order = 'id desc'
    _log_access = False
    _rec_name = 'event'

    date = fields.Datetime(required=True, default=fields.Datetime.now, index=True, readonly=True)
    user_id = fields.Many2one('res.users', string='User', index=True, readonly=True, ondelete='set null')
    login = fields.Char(readonly=True, help="The login typed, for a failed sign-in.")
    event = fields.Selection(EVENTS, required=True, index=True, readonly=True)
    model = fields.Char(string='Model', index=True, readonly=True)
    model_name = fields.Char(string='Data', compute='_compute_model_name')
    res_id = fields.Many2oneReference(string='Record', model_field='model', readonly=True)
    res_name = fields.Char(string='Record Name', readonly=True)
    method = fields.Char(readonly=True)
    record_count = fields.Integer(string='Records', readonly=True)
    record_ids = fields.Char(string='Record Ids', readonly=True,
                             help="The first ids of the records read, printed or exported.")
    detail = fields.Text(readonly=True)
    changes = fields.Text(readonly=True)
    ip = fields.Char(string='Address', readonly=True)
    user_agent = fields.Char(string='Browser', readonly=True)

    @api.depends('model')
    def _compute_model_name(self):
        IrModel = self.env['ir.model'].sudo()
        names = {}
        for line in self:
            if line.model not in names:
                names[line.model] = IrModel._get(line.model).name if line.model in self.env else line.model
            line.model_name = names[line.model] or False

    def _compute_display_name(self):
        labels = dict(self._fields['event']._description_selection(self.env))
        for line in self:
            line.display_name = ' '.join(filter(None, (labels.get(line.event), line.res_name or line.model)))

    #
    # writing lines
    #

    @api.model
    def _om_values(self, event, **values):
        values = dict(values, event=event)
        values.setdefault('user_id', self.env.uid)
        values.setdefault('date', fields.Datetime.now())
        for key, value in request_context().items():
            values.setdefault(key, value)
        if 'record_ids' in values and not isinstance(values['record_ids'], str):
            ids = list(values['record_ids'] or ())
            values.setdefault('record_count', len(ids))
            values['record_ids'] = ','.join(map(str, ids[:RECORD_IDS_KEPT])) + (',...' if len(ids) > RECORD_IDS_KEPT else '')
        return values

    @api.model
    def _om_log(self, event, separate=False, **values):
        """ Log an event of another module: ``refused``, ``other``... With
        ``separate``, the line is written on a cursor of its own once the
        transaction ends, and survives its rollback. """
        values = self._om_values(event, **values)
        if separate:
            self._om_after_transaction([values])
        else:
            self._om_buffer([values])

    @api.model
    def _om_buffer(self, vals_list):
        """ Write the lines with the transaction, or after it on a read-only one. """
        if not vals_list:
            return
        cr = self.env.cr
        if cr.readonly:
            self._om_after_transaction(vals_list)
            return
        data = cr.precommit.data
        if BUFFER_KEY not in data:
            data[BUFFER_KEY] = []
            cr.precommit.add(self._om_flush)
        data[BUFFER_KEY].extend(vals_list)

    def _om_flush(self):
        lines = self.env.cr.precommit.data.pop(BUFFER_KEY, [])
        if lines:
            self.sudo().with_context(om_user_audit_off=True).create(lines)

    @api.model
    def _om_after_transaction(self, vals_list):
        cr = self.env.cr
        if cr.readonly and module.current_test:
            # tests cannot open a read/write cursor from a read-only one once it
            # is in use: roll it back and write now, as res.device.log does
            cr.rollback()
            self._om_write_separately(self.env.registry, vals_list)
            return
        lines = cr.postcommit.data.get(BUFFER_KEY)
        if lines is None:
            # the hooks hold the list itself: a rollback clears the postcommit
            # data before it runs the postrollback hooks
            lines = cr.postcommit.data[BUFFER_KEY] = []
            registry = self.env.registry

            def flush():
                pending = lines[:]
                lines.clear()
                if pending:
                    self._om_write_separately(registry, pending)
            cr.postcommit.add(flush)
            cr.postrollback.add(flush)
        lines.extend(vals_list)

    @api.model
    def _om_write_separately(self, registry, vals_list):
        try:
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {'om_user_audit_off': True})
                env[self._name].create(vals_list)
        except Exception:
            _logger.warning("Could not write %s audit lines", len(vals_list), exc_info=True)

    #
    # retention
    #

    @api.model
    def _cron_clean(self):
        params = self.env['ir.config_parameter'].sudo()
        days = params.get_int('om_user_audit.keep_days', 90)
        sign_in_days = params.get_int('om_user_audit.keep_sign_in_days') or days
        if days > 0:
            self._om_delete_before(fields.Datetime.now() - timedelta(days=days),
                                   [('event', 'not in', ('login', 'login_failed', 'logout', 'session_end'))])
        if sign_in_days > 0:
            self._om_delete_before(fields.Datetime.now() - timedelta(days=sign_in_days),
                                   [('event', 'in', ('login', 'login_failed', 'logout', 'session_end'))])

    def _om_delete_before(self, limit_date, domain, batch=10000):
        while True:
            lines = self.sudo().search(domain + [('date', '<', limit_date)], limit=batch, order='id')
            if not lines:
                return
            self.env.cr.execute("DELETE FROM om_user_audit_log WHERE id IN %s", [tuple(lines.ids)])
            if self.env.context.get('ir_cron_progress_id'):
                self.env['ir.cron']._commit_progress(len(lines))
            if len(lines) < batch:
                return

    #
    # screens
    #

    def action_open_record(self):
        self.ensure_one()
        if not (self.model and self.res_id and self.model in self.env):
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.model,
            'res_id': self.res_id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _om_lines_per_day(self):
        self.env.cr.execute(
            "SELECT count(*) FROM om_user_audit_log WHERE date > now() at time zone 'UTC' - interval '1 day'")
        return self.env.cr.fetchone()[0]

    def _om_event_label(self):
        return dict(self._fields['event']._description_selection(self.env)).get(self.event, self.event)

    @api.model
    def _om_today_message(self):
        return _("%s lines in the last 24 hours", self._om_lines_per_day())
