# The approval rules stop the buttons clicked in the web client, which call call_button, and the same methods
# called by hand through call_kw. Both routes, and the older /web/dataset/call, run their method through
# _call_kw. Server code calling a method directly is never stopped. A button running once approved may change its
# record, which the approval locks, until the end of the call.
from odoo.http import request

from odoo.addons.web.controllers.dataset import DataSet


class DataSetApproval(DataSet):

    def _call_kw(self, model, method, args, kwargs):
        Request = request.env['approval.request']
        action = Request._gate_call(model, method, args)
        if action is not None:
            return action
        try:
            return super()._call_kw(model, method, args, kwargs)
        finally:
            Request._restore_lock()
