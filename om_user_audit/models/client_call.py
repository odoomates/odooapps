# The calls a client or a script makes itself (web client, XML-RPC),
# told apart from Odoo's own code, which reads and writes data on its own.
import threading
from contextvars import ContextVar

from odoo import models
from odoo.http import request
from odoo.service import model as service_model

# XML-RPC and JSON-RPC run without a request: their controllers keep the
# client's address here
RPC_ADDRESS = ContextVar('om_user_audit_rpc_address', default=None)
# the method an XML-RPC or JSON-RPC call names: Odoo 15 keeps no trace of it
RPC_CALL = threading.local()


def marking_rpc_calls(execute_cr):
    if getattr(execute_cr, 'om_marking', False):
        return execute_cr

    def execute(cr, uid, obj, method, *args, **kw):
        RPC_CALL.model_method = f'{obj}.{method}'
        try:
            return execute_cr(cr, uid, obj, method, *args, **kw)
        finally:
            RPC_CALL.model_method = ''
    execute.om_marking = True
    return execute


service_model.execute_cr = marking_rpc_calls(service_model.execute_cr)


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
        # Odoo 15 keeps the request of an XML-RPC call bound: the marker comes first
        marker = getattr(RPC_CALL, 'model_method', None)
        if marker:
            return marker == f'{self._name}.{method}'
        if request:
            entry = getattr(request, 'om_rpc_entry', None)
            return bool(entry) and entry[0] == self._name and entry[1] in (method, '*')
        return False
