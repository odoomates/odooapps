# The signed-in browsers and devices. Odoo 15 keeps no list of them (res.device
# comes with 17.2): each session notes itself on its requests, at most once a
# minute, under a hash of its id, never the id itself. Ending one marks it
# revoked: its next request signs it out.
import hashlib
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied
from odoo.http import request

PLATFORMS = (('Android', 'android'), ('iPhone', 'iphone'), ('iPad', 'ipad'), ('Windows', 'windows'),
             ('Mac', 'macintosh|mac os'), ('Linux', 'linux'), ('ChromeOS', 'cros'))
BROWSERS = (('Edge', r'edg/'), ('Opera', r'opr/|opera'), ('Chrome', r'chrome/|crios/'),
            ('Firefox', r'firefox/|fxios/'), ('Safari', r'safari/'))


def session_identifier(sid):
    return hashlib.sha256(sid.encode()).hexdigest()


def describe_agent(agent):
    """ (platform, browser) of a user agent string. """
    agent = (agent or '').lower()
    platform = next((name for name, pattern in PLATFORMS if re.search(pattern, agent)), False)
    browser = next((name for name, pattern in BROWSERS if re.search(pattern, agent)), False)
    return platform, browser


class OmUserAuditSession(models.Model):
    _name = 'om.user.audit.session'
    _description = 'Signed-in Session'
    _order = 'last_activity desc'

    session_identifier = fields.Char(required=True, index=True, readonly=True)
    user_id = fields.Many2one('res.users', string='User', index=True, readonly=True, ondelete='cascade')
    ip_address = fields.Char(string='IP Address', readonly=True)
    platform = fields.Char(readonly=True)
    browser = fields.Char(readonly=True)
    country = fields.Char(readonly=True)
    city = fields.Char(readonly=True)
    first_activity = fields.Datetime(readonly=True)
    last_activity = fields.Datetime(readonly=True, index=True)
    revoked = fields.Boolean(readonly=True, index=True)
    is_current = fields.Boolean(string='This Session', compute='_compute_is_current')
    om_idle = fields.Boolean(string='Idle', compute='_compute_om_idle')

    def _compute_is_current(self):
        current = request and request.session.sid and session_identifier(request.session.sid)
        for session in self:
            session.is_current = bool(current) and session.session_identifier == current

    @api.depends('last_activity')
    def _compute_om_idle(self):
        minutes = self.env['ir.config_parameter'].sudo().get_int('om_user_audit.idle_minutes')
        limit = fields.Datetime.now() - timedelta(minutes=minutes or 60)
        for session in self:
            session.om_idle = bool(session.last_activity and session.last_activity < limit)

    @api.model
    def _om_note_request(self, uid, refresh):
        """ On a request of a signed-in session: refuse it if the session was
        ended, else note it (``refresh``: its activity is old enough to note).
        Return False when the session was ended. """
        identifier = session_identifier(request.session.sid)
        session = self.sudo().search([('session_identifier', '=', identifier)], limit=1)
        if session.revoked:
            return False
        if session and not refresh:
            return True
        now = fields.Datetime.now()
        if session:
            session.write({'last_activity': now, 'ip_address': request.httprequest.remote_addr})
            return True
        platform, browser = describe_agent(request.httprequest.user_agent.string)
        geoip = request.session.get('geoip') or {}
        city = geoip.get('city')
        self.sudo().create({
            'session_identifier': identifier, 'user_id': uid, 'platform': platform, 'browser': browser,
            'ip_address': request.httprequest.remote_addr,
            'country': geoip.get('country_name') or False,
            'city': city if isinstance(city, str) else False,
            'first_activity': now, 'last_activity': now,
        })
        return True

    def _revoke(self):
        self.sudo().write({'revoked': True})

    def action_om_end(self):
        """ End the sessions, whoever they belong to (Settings users only). """
        if not self.env.user.has_group('base.group_system'):
            raise AccessDenied()
        Log = self.env['om.user.audit.log']
        for session in self:
            Log._om_log('session_end', user_id=session.user_id.id, ip=session.ip_address,
                        detail=f'by {self.env.user.login}')
        self._revoke()
        return True

    @api.model
    def _cron_end_idle(self):
        minutes = self.env['ir.config_parameter'].sudo().get_int('om_user_audit.idle_minutes')
        params = self.env['ir.config_parameter'].sudo()
        Log = self.env['om.user.audit.log']
        if minutes > 0:
            # the requests do the precise check; this ends the ones nobody uses any more
            limit = fields.Datetime.now() - timedelta(minutes=max(minutes, 60) + 60)
            sessions = self.sudo().search([('revoked', '=', False), ('last_activity', '<', limit)])
            for session in sessions:
                Log._om_log('session_end', user_id=session.user_id.id, ip=session.ip_address, detail='idle')
            sessions._revoke()
        # forget the ended sessions after a while
        days = params.get_int('om_user_audit.keep_sign_in_days') or params.get_int('om_user_audit.keep_days', 90)
        self.sudo().search([('revoked', '=', True),
                            ('last_activity', '<', fields.Datetime.now() - timedelta(days=days))]).unlink()
