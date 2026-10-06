# The calls a client or a script makes itself (web client, JSON-2, XML-RPC),
# told apart from Odoo's own code, which reads and writes data on its own.
from contextvars import ContextVar

from odoo import models
from odoo.http import request
from odoo.service.server import thread_local

# XML-RPC and JSON-RPC run without a request: their controllers keep the
# client's address here
RPC_ADDRESS = ContextVar('om_user_audit_rpc_address', default=None)


def mark_rpc_entry(model_name, method):
    """ Record, on the current request, the method a client called. """
    if request:
        request.om_rpc_entry = (model_name, method)


def client_address():
    """ The address of the client: the request's, else the one kept by the RPC controllers. """
    if request:
        return request.httprequest.remote_addr
    return RPC_ADDRESS.get()


class Base(models.AbstractModel):
    _inherit = 'base'

    def _om_rpc_entry(self, method):
        """ Whether ``method`` of this model is the call the client or the script made. """
        if self.env.su:
            return False
        if request:
            entry = getattr(request, 'om_rpc_entry', None)
            return bool(entry) and entry[0] == self._name and entry[1] in (method, '*')
        marker = getattr(thread_local, 'rpc_model_method', None)
        return marker == f'{self._name}.{method}'
