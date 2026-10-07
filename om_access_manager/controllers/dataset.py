# Server side blocking of object buttons, on call_button and on call_kw (callable
# by hand). Server code never goes through either, so it is never blocked.
from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.dataset import DataSet

from ..models.om_access_preview import preview_allowed, preview_of_request

# Not button checked: denying these is Base._access_domain()'s job.
PROTECTED_METHODS = frozenset({
    'create', 'write', 'unlink', 'web_search_read',
    'read', 'search', 'search_read', 'onchange', 'copy', 'default_get',
})


def _record_ids(args):
    ids = args[0] if args else None
    if isinstance(ids, int) and not isinstance(ids, bool):
        return [ids]
    if isinstance(ids, (list, tuple)) and all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return list(ids)
    return None


class DataSetAccess(DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        if method not in PROTECTED_METHODS:
            request.env['om.access.profile']._check_button(model, 'object', method, _record_ids(args))
        return super().call_kw(model, method, args, kwargs, path=path)

    @http.route()
    def call_button(self, model, method, args, kwargs):
        if method not in PROTECTED_METHODS:
            request.env['om.access.profile']._check_button(model, 'object', method, _record_ids(args))
        if preview_of_request():
            raise preview_allowed()
        return super().call_button(model, method, args, kwargs)

    @http.route()
    def resequence(self, model, ids, field='sequence', offset=0):
        # Odoo 16 reorders the rows here, not through web_resequence: a field
        # the profile hides or makes read-only is not reordered either
        Model = request.env[model]
        rules = Model._om_field_rules()
        if rules and field in Model._om_locked(rules, model):
            Model._om_refuse(model, field)
        return super().resequence(model, ids, field=field, offset=offset)
