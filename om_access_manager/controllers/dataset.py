# Server side blocking of object buttons, on call_button and on call_kw (callable
# by hand). Server code never goes through either, so it is never blocked.
from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.dataset import DataSet

from ..models.field_guard import mark_rpc_entry

# Not button checked: denying these is Base._access_domain()'s job.
PROTECTED_METHODS = frozenset({
    'create', 'write', 'unlink', 'web_save', 'web_read', 'web_search_read',
    'read', 'search', 'search_read', 'onchange', 'copy', 'default_get',
})


class DataSetAccess(DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        if method not in PROTECTED_METHODS:
            request.env['om.access.profile']._check_button(model, 'object', method)
        mark_rpc_entry(model, method)
        return super().call_kw(model, method, args, kwargs, path=path)

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        if method not in PROTECTED_METHODS:
            request.env['om.access.profile']._check_button(model, 'object', method)
        mark_rpc_entry(model, method)
        return super().call_button(model, method, args, kwargs, path=path)
