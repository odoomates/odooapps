# XML-RPC and JSON-RPC (/xmlrpc/2/object, /jsonrpc): the same button check as
# call_kw (dataset.py). Their routes run without a database, so overriding the
# controllers would not apply: wrap the function they call instead.
from odoo.service import model as service_model

from .dataset import PROTECTED_METHODS, _record_ids


def with_button_check(execute_cr):
    if getattr(execute_cr, 'om_button_check', False):
        return execute_cr

    def checked_execute_cr(cr, uid, obj, method, *args, **kw):
        # every database of the server goes through here, installed or not
        from odoo import api  # noqa: PLC0415
        env = api.Environment(cr, uid, {})
        if method not in PROTECTED_METHODS and 'om.access.profile' in env:
            env['om.access.profile']._check_button(obj, 'object', method, _record_ids(args))
        return execute_cr(cr, uid, obj, method, *args, **kw)
    checked_execute_cr.om_button_check = True
    return checked_execute_cr


service_model.execute_cr = with_button_check(service_model.execute_cr)
