from odoo import http
from odoo.http import request

from odoo.addons.rpc.controllers.json2 import WebJson2Controller


class WebJson2Approval(WebJson2Controller):
    """ POST /json/2/<model>/<method>: a button waiting for an approval asks for it instead of running. """

    @http.route()
    def web_json_2_rpc(self, __model__, __method__, ids=(), context=None, **kwargs):
        Request = request.env['approval.request']
        action = Request._gate_call(__model__, __method__, [list(ids)], api=True) if ids else None
        if action is not None:
            return action
        try:
            return super().web_json_2_rpc(__model__, __method__, ids=ids, context=context or {}, **kwargs)
        finally:
            Request._restore_lock()
