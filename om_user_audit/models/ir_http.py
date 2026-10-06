# Sign-outs, and the sessions idle for longer than the settings allow.
import time

from odoo import SUPERUSER_ID, api, models
from odoo.http import request

SEEN_KEY = 'om_user_audit_seen'
# the session is saved at most this often to note the last request
SEEN_PRECISION = 60


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        uid = request and request.session.uid
        if uid:
            cls._om_check_idle(uid)
        return super()._authenticate(endpoint)

    @classmethod
    def _om_check_idle(cls, uid):
        env = api.Environment(request.env.cr, SUPERUSER_ID, {})
        minutes = env['ir.config_parameter'].get_int('om_user_audit.idle_minutes')
        now = time.time()
        seen = request.session.get(SEEN_KEY)
        if minutes > 0 and seen and now - seen > minutes * 60:
            env['om.user.audit.log']._om_log('session_end', separate=True, user_id=uid, detail='idle')
            request.session.logout(keep_db=True)
            request.env = api.Environment(request.env.cr, None, request.env.context)
            return
        refresh = not seen or now - seen > SEEN_PRECISION
        if not env['om.user.audit.session']._om_note_request(uid, refresh):
            # ended from the Sessions list, where it was logged
            request.session.logout(keep_db=True)
            request.env = api.Environment(request.env.cr, None, request.env.context)
            return
        if refresh:
            request.session[SEEN_KEY] = now

    @classmethod
    def _om_log_logout(cls):
        uid = request and request.session.uid
        if uid:
            env = api.Environment(request.env.cr, SUPERUSER_ID, {})
            env['om.user.audit.log']._om_log('logout', separate=True, user_id=uid)
