# The profiles a user carries, and the export group this module hides on purpose.
import hashlib

from odoo import SUPERUSER_ID, _, api, fields, models, tools
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.tools import LazyTranslate

from odoo.addons.om_user_audit.models.client_call import client_address

from .login_tools import utc_now

EXPORT_GROUP = 'base.group_allow_export'
_lt = LazyTranslate(__name__)
LOGIN_REFUSALS = {
    'hours': _lt("Your access profile only allows signing in during your working hours."),
    'network': _lt("Your access profile does not allow signing in from this network."),
}
# session key holding the sign-in moment (One Session per User)
LOGIN_STAMP_KEY = 'om_access_login_stamp'
USER_FIELDS_IN_FILTERS = ('company_ids', 'property_warehouse_id')


class ResUsers(models.Model):
    _inherit = 'res.users'

    access_allowed_ids = fields.One2many(
        'om.access.allowed', 'user_id', string='Allowed Records', groups='om_access_manager.group_access_manager',
        help="The records of this user, for the profiles whose allowed records are "
             "'each user's own': their point of sale, their warehouse...")
    access_assignment_ids = fields.One2many(
        'om.access.profile.assignment', 'user_id', string='Temporary Profiles',
        groups='om_access_manager.group_access_manager')
    om_access_login_stamp = fields.Float(
        copy=False, groups='om_access_manager.group_access_manager',
        help="When the user last signed in, for One Session per User.")
    access_effective = fields.Html(
        string='Effective Access', compute='_compute_access_effective', sanitize=False,
        groups='om_access_manager.group_access_manager',
        help="What this user really ends up with, all of their profiles combined.")
    access_profile_ids = fields.Many2many(
        'om.access.profile', 'om_access_profile_users_rel', 'uid', 'profile_id',
        string='Access Profiles', groups='om_access_manager.group_access_manager',
        help="A user may carry several profiles. Additive profiles combine "
             "permissively, override profiles always subtract.")

    @classmethod
    def _login(cls, db, credential, user_agent_env):
        # Odoo 18 signs in on a cursor of its own: so is the stamp written
        auth_info = super()._login(db, credential, user_agent_env)
        uid = auth_info.get('uid')
        if uid and request:
            with cls.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                rules = env['om.access.profile']._resolve(uid)
                if rules.enabled and rules.has_flag('single_session'):
                    # an older session than the user's stamp ends on its next
                    # request (ir_http.py)
                    stamp = utc_now().timestamp()
                    request.session[LOGIN_STAMP_KEY] = stamp
                    env['res.users'].browse(uid).om_access_login_stamp = stamp
        return auth_info

    @api.depends('access_profile_ids', 'access_allowed_ids')
    def _compute_access_effective(self):
        Report = self.env['om.access.test.user']
        for user in self:
            user.access_effective = Report.new({'user_id': user.id}).report if user.id else False

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        internal = users.filtered(lambda user: not user.share)
        if internal:
            profiles = self.env['om.access.profile'].sudo().search([('for_new_users', '=', True)])
            if profiles:
                internal.sudo().write({'access_profile_ids': [(4, profile.id) for profile in profiles]})
        return users

    def write(self, vals):
        before = self.sudo().access_profile_ids if 'access_profile_ids' in vals else None
        result = super().write(vals)
        if 'access_profile_ids' in vals:
            (before | self.sudo().access_profile_ids)._sync_group()
            # the guard against locking every administrator out applies here too
            self.sudo().access_profile_ids._check_last_administrator()
            self.env.registry.clear_cache('default')
        elif vals.get('active') is False or 'groups_id' in vals:
            # archiving, or taking out of Access Management, the last access
            # manager the profiles leave able to undo them
            self.env['om.access.profile'].sudo().search([])._check_last_administrator()
        elif not set(vals).isdisjoint(USER_FIELDS_IN_FILTERS) or not set(vals).isdisjoint(
                self.env['om.access.profile']._om_user_fields_in_filters()):
            # _resolve() depends on the user's companies, and record filters
            # read the default warehouse
            self.env.registry.clear_cache('default')
        return result

    def has_group(self, group_ext_id):
        result = super().has_group(group_ext_id)
        if not result or group_ext_id != EXPORT_GROUP:
            return result
        if self.id != self.env.uid:
            return result
        # The Export menu, export_data() and the export controller all check this
        # group. env.user is sudo, so the rules are resolved for self.id.
        rules = self.env['om.access.profile']._resolve(self.id)
        if rules.enabled and rules.has_flag('block_export'):
            return False
        return result

    def _check_credentials(self, credential, env):
        result = super()._check_credentials(credential, env)
        # Odoo 18 checks the credentials of XML-RPC calls on an empty recordset
        for user in self or self.env.user:
            rules = self.env['om.access.profile']._resolve(user.id)
            if not rules.enabled:
                continue
            # after super(), so it covers every kind of credential once accepted
            if rules.has_flag('block_login'):
                raise AccessDenied(_("Your access profile does not allow you to sign in."))
            reason = rules.login_refusal(utc_now(), client_address())
            if reason:
                raise AccessDenied(self.env._(LOGIN_REFUSALS[reason]))
            # 'interactive' is False for XML-RPC/JSON-RPC sign-ins, True for the browser
            if not env.get('interactive', True) and rules.has_flag('block_rpc'):
                raise AccessDenied(_(
                    "Your access profile does not allow signing in through "
                    "the external API."))
        return result

    @tools.ormcache('sid')
    def _compute_session_token(self, sid):
        # The session token is checked on every request, so changing it while
        # the login is blocked ends the sessions already open. Odoo 18 computes
        # it in SQL from the columns of the user: change it here.
        token = super()._compute_session_token(sid)
        if token:
            rules = self.env['om.access.profile']._resolve(self.id)
            if rules.enabled and rules.has_flag('block_login'):
                token = hashlib.sha256(f'{token}:om_access_block_login'.encode()).hexdigest()
        return token

    @api.model
    def _get_access_profile_action(self):
        return self.env.ref('om_access_manager.om_access_profile_action').sudo().read()[0]
