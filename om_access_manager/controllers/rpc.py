# XML-RPC and JSON-RPC (/xmlrpc/2/object, /jsonrpc): the same button check as
# call_kw (dataset.py). Their routes run without a database, so overriding the
# controllers would not apply: wrap the function they call instead, which the
# web client and JSON-2 import under their own name and do not go through.
from odoo.service import model as service_model

from .dataset import PROTECTED_METHODS, _record_ids


def with_button_check(call_kw):
    if getattr(call_kw, 'om_button_check', False):
        return call_kw

    def checked_call_kw(model, name, args, kwargs):
        # every database of the server goes through here, installed or not
        if name not in PROTECTED_METHODS and 'om.access.profile' in model.env:
            model.env['om.access.profile']._check_button(model._name, 'object', name, _record_ids(args))
        return call_kw(model, name, args, kwargs)
    checked_call_kw.om_button_check = True
    return checked_call_kw


service_model.call_kw = with_button_check(service_model.call_kw)
