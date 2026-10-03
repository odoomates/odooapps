# The JSON-2 API: the same checks as the web client's call_kw (dataset.py).
from odoo import http
from odoo.http import request

from odoo.addons.rpc.controllers.json2 import WebJson2Controller

from ..models.field_guard import mark_rpc_entry
from .dataset import PROTECTED_METHODS


class WebJson2Access(WebJson2Controller):

    @http.route()
    def web_json_2_rpc(self, __model__, __method__, *args, **kwargs):
        if __method__ not in PROTECTED_METHODS:
            request.env['om.access.profile']._check_button(__model__, 'object', __method__)
        mark_rpc_entry(__model__, __method__)
        return super().web_json_2_rpc(__model__, __method__, *args, **kwargs)
