""" XML-RPC and JSON-RPC call the methods of the models through the object service, which no controller sees:
its ``call_kw`` is wrapped, so that a button waiting for an approval asks for it instead of running, in the
databases where Approvals is installed. """
from odoo.service import model as object_service

_call_kw = object_service.call_kw


def call_kw(model, name, args, kwargs):
    if 'approval.request' not in model.env:
        return _call_kw(model, name, args, kwargs)
    Request = model.env['approval.request']
    action = Request._gate_call(model._name, name, args, api=True)
    if action is not None:
        return action
    try:
        return _call_kw(model, name, args, kwargs)
    finally:
        Request._restore_lock()


if getattr(object_service.call_kw, '__module__', None) != __name__:
    object_service.call_kw = call_kw
