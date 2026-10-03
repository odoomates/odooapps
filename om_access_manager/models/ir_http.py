# _handle_debug() is the single place the debug flag enters the session, so
# clearing it there blocks developer mode from the menu and the URL alike.
from odoo import SUPERUSER_ID, _, api, models
from odoo.exceptions import AccessDenied

from .login_tools import utc_now
from .res_users import LOGIN_STAMP_KEY


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _handle_debug(cls):
        super()._handle_debug()
        from odoo.http import request  # noqa: PLC0415
        if not request or not request.session.debug:
            return
        # /odoo is an auth='none' route: the env has no user yet, the session does.
        uid = (request.env and request.env.uid) or request.session.uid
        if not uid:
            return
        rules = request.env(user=uid)['om.access.profile']._current_rules()
        if rules.enabled and rules.has_flag('block_developer_mode'):
            request.session.debug = ''


class IrHttpHome(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        if self.env.uid:
            rules = self.env['om.access.profile']._resolve(self.env.uid)
            if rules.enabled and (home := rules.home_action()):
                result['home_action_id'] = home
        return result


class IrHttpSignIn(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate_explicit(cls, routing):
        # Logging a refused session out before the standard check makes Odoo
        # answer as for any expired session: back to the sign-in page.
        from odoo.http import request  # noqa: PLC0415
        from odoo.http.session import logout  # noqa: PLC0415
        uid = request and request.session.uid
        if uid:
            env = api.Environment(request.env.cr, SUPERUSER_ID, {})
            rules = env['om.access.profile']._resolve(uid)
            if rules.enabled and cls._om_session_refused(env, rules, uid):
                logout(request.session, keep_db=True)
                # the env was built from the session before this check; drop the user
                request.env = api.Environment(request.env.cr, None, request.env.context)
        elif request and request.env and request.env.uid:
            # an API key (JSON-2) bypasses the session and _check_credentials
            env = api.Environment(request.env.cr, SUPERUSER_ID, {})
            rules = env['om.access.profile']._resolve(request.env.uid)
            if rules.enabled and (
                    rules.has_flag('block_login') or rules.has_flag('block_rpc')
                    or rules.login_refusal(utc_now(), request.httprequest.remote_addr)):
                raise AccessDenied(_("Your access profile does not allow this sign-in."))
        return super()._authenticate_explicit(routing)

    @classmethod
    def _om_session_refused(cls, env, rules, uid):
        from odoo.http import request  # noqa: PLC0415
        if rules.has_flag('block_login'):
            return True
        if rules.login_refusal(utc_now(), request.httprequest.remote_addr):
            return True
        if rules.has_flag('single_session'):
            latest = env['res.users'].browse(uid).om_access_login_stamp
            return bool(latest) and request.session.get(LOGIN_STAMP_KEY, 0) < latest
        return False
