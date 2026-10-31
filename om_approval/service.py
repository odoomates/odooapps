""" XML-RPC and JSON-RPC call the methods of the models through the object service, which no controller sees:
its ``execute_cr`` is wrapped, so that a button waiting for an approval asks for it instead of running, in the
databases where Approvals is installed. The data files call ``odoo.api.call_kw`` too, so that one is left alone. """
from functools import partial

from odoo import _, api
from odoo.exceptions import UserError
from odoo.service import model as object_service
from odoo.tools import lazy

_execute_cr = object_service.execute_cr


def call_kw(model, name, args, kwargs):
    Request = model.env['approval.request']
    action = Request._gate_call(model._name, name, args, api=True)
    if action is not None:
        return action
    try:
        return api.call_kw(model, name, args, kwargs)
    finally:
        Request._restore_lock()


def execute_cr(cr, uid, obj, method, *args, **kw):
    env = api.Environment(cr, uid, {})
    if 'approval.request' not in env:
        return _execute_cr(cr, uid, obj, method, *args, **kw)
    # the same as the object service, calling the call_kw above
    cr.reset()
    recs = env.get(obj)
    if recs is None:
        raise UserError(_("Object %s doesn't exist", obj))
    object_service.get_public_method(recs, method)
    result = object_service.retrying(partial(call_kw, recs, method, args, kw), env)
    # force evaluation of lazy values before the cursor is closed
    for value in object_service._traverse_containers(result, lazy):
        value._value  # noqa: B018
    return result


if getattr(object_service.execute_cr, '__module__', None) != __name__:
    object_service.execute_cr = execute_cr
