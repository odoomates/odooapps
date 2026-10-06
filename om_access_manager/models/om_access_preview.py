# Preview as a user: the administrator's session shows Odoo as another user
# sees it (their groups, their profiles, their records), read only. The
# session keeps the administrator signed in; each request is served as the
# previewed user on a read-only transaction, so nothing can be saved.
import time

from psycopg2.errors import ReadOnlySqlTransaction

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request

PREVIEW_KEY = 'om_access_preview'
PREVIEW_SECONDS = 3600
MANAGER_GROUP = 'om_access_manager.group_access_manager'


def preview_of_request():
    """ The preview the current request is served in, or None. """
    return getattr(request, 'om_preview', None) if request else None


def preview_refused():
    return UserError(_("This is a preview: nothing is saved."))


def preview_allowed():
    """ A button the previewed user may use: said, not run. """
    name = request.env.user.sudo().name
    return UserError(_("%s may use this. It is not run in a preview.", name))


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _om_preview_refusal(self, viewer):
        """ Why ``viewer`` may not preview this user, or None. """
        self.ensure_one()
        if not viewer.has_group(MANAGER_GROUP):
            return _("Only access managers can preview a user.")
        if self == viewer:
            return _("You cannot preview yourself.")
        if not self.active or self.share:
            return _("Only active internal users can be previewed.")
        if self.id in self.env['om.access.profile']._exempt_user_ids():
            return _("The administrator is never restricted: there is nothing to preview.")
        # nobody reads more through a preview than they can already
        if not viewer.has_group('base.group_system') and not self.groups_id <= viewer.groups_id:
            return _("%s has rights you do not have: only a Settings user can preview them.", self.name)
        return None

    def action_om_preview(self, back_url=None):
        """ Start previewing this user in the current session. """
        self.ensure_one()
        target = self.sudo()
        viewer = self.env.user.sudo()
        reason = target._om_preview_refusal(viewer)
        if reason:
            raise AccessError(reason)
        if not request:
            raise UserError(_("A preview needs a browser session."))
        if 'res.users.settings' in self.env:
            # Odoo 17 creates them on the first page load, and a preview is read only
            self.env['res.users.settings'].sudo()._find_or_create_for_user(target)
        request.session[PREVIEW_KEY] = {
            'uid': target.id,
            'by': viewer.id,
            'until': time.time() + PREVIEW_SECONDS,
            'back': back_url or f'/web#action=base.action_res_users&id={target.id}&view_type=form',
            'cids': request.httprequest.cookies.get('cids'),
            'context': dict(request.session.context),
        }
        self.env['om.user.audit.log']._om_log(
            'other', separate=True, detail=_("Preview as %s started", target.name))
        # the screens of the user are cached per user: start from a clean page
        return {'type': 'ir.actions.act_url', 'url': '/web', 'target': 'self'}

    @api.model
    def _om_preview_stop(self):
        data = request.session.pop(PREVIEW_KEY, None) if request else None
        if data:
            # the web client's session info gave the session the user's language
            request.session.context = data.get('context') or request.session.context
            # attributed to the administrator by the audit override below
            self.env['om.user.audit.log']._om_log('other', separate=True, detail=_("Preview ended"))
        return data


def valid_preview(env):
    """ The preview of the session, checked again on every request: still
    the same administrator, not expired, still allowed. None otherwise. """
    data = request.session.get(PREVIEW_KEY)
    if not data:
        return None
    viewer = env['res.users'].sudo().browse(request.session.uid)
    target = env['res.users'].sudo().browse(data.get('uid')).exists()
    if (data.get('by') == request.session.uid and data.get('until', 0) > time.time()
            and target and not target._om_preview_refusal(viewer)):
        return data
    request.session.pop(PREVIEW_KEY, None)
    return None


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        if not request.env.uid or request.env.uid != request.session.uid:
            return
        data = valid_preview(request.env)
        if not data:
            return
        request.om_preview = data
        target = request.env['res.users'].sudo().browse(data['uid'])
        request.update_env(user=target.id)
        request.update_context(**{key: value for key, value in target.context_get().items()
                                  if key in ('lang', 'tz')})
        # whatever the request does from here, the database refuses to write it
        request.env.cr.execute('SET TRANSACTION READ ONLY')

    @classmethod
    def _dispatch(cls, endpoint):
        if not preview_of_request():
            return super()._dispatch(endpoint)
        try:
            result = super()._dispatch(endpoint)
            request.env.flush_all()
        except ReadOnlySqlTransaction:
            raise preview_refused() from None
        finally:
            # nothing was written: end the read-only transaction here
            request.env.cr.rollback()
        return result

    def session_info(self):
        data = preview_of_request()
        if not data and request and self.env.uid and self.env.uid == request.session.uid:
            # /web is served without a user: the preview is read from the session
            data = valid_preview(self.env)
        elif not data and request and self.env.context.get('om_preview'):
            data = request.session.get(PREVIEW_KEY)
        if data and self.env.uid == data['by']:
            return self.with_user(data['uid']).with_context(om_preview=True).session_info()
        result = super().session_info()
        if data and self.env.uid == data['uid']:
            result['uid'] = data['uid']
            viewer = self.env['res.users'].sudo().browse(data['by'])
            rules = self.env['om.access.profile']._resolve(data['uid'])
            result['om_preview'] = {
                'name': self.env.user.sudo().name,
                'viewer': viewer.name,
                'profiles': [rule.name for rule in rules.additive + rules.override],
                'until': data['until'],
            }
            result['om_access_classes'] = [*result.get('om_access_classes', []), 'o_om_preview']
        return result


class Base(models.AbstractModel):
    _inherit = 'base'

    # refused before the database does it, which would log the query as an error

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and preview_of_request():
            raise preview_refused()
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and preview_of_request():
            raise preview_refused()
        return super().write(vals)

    def unlink(self):
        if not self.env.su and preview_of_request():
            raise preview_refused()
        return super().unlink()


class OmUserAuditLog(models.Model):
    _inherit = 'om.user.audit.log'

    def _om_values(self, event, **values):
        # what is read during a preview is read by the person previewing
        values = super()._om_values(event, **values)
        data = preview_of_request()
        if data:
            name = self.env['res.users'].sudo().browse(data['uid']).name
            values['user_id'] = data['by']
            values['detail'] = ' — '.join(filter(None, [_("Preview as %s", name), values.get('detail')]))
        return values

    @api.model
    def _om_buffer(self, vals_list):
        # the transaction of a preview is read only: write the lines after it
        if preview_of_request():
            return self._om_after_transaction(vals_list)
        return super()._om_buffer(vals_list)
