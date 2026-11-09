from odoo import _, http
from odoo.http import request

from odoo.addons.web.controllers.dataset import DataSet


def _record_ids(args):
    ids = args[0] if args else None
    if isinstance(ids, int) and not isinstance(ids, bool):
        return [ids]
    if isinstance(ids, (list, tuple)) and ids and all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        return list(ids)
    return None


class DataSetWorkflow(DataSet):
    """ A button a published workflow starts on goes on only for the records
    the workflow lets through: the others wait for their approval. Only a
    click is checked, never the code that calls the same method. """

    @http.route()
    def call_button(self, model, method, args, kwargs):
        ids = _record_ids(args)
        Workflow = request.env['om.workflow'].with_context(**((kwargs or {}).get('context') or {}))
        gate = ids and Workflow._button_gate(model, method, ids)
        if not gate:
            return super().call_button(model, method, args, kwargs)
        allowed, messages = gate
        action = False
        if allowed:
            action = super().call_button(model, method, [allowed, *args[1:]], kwargs)
        params = {
            'title': _("Waiting for approval"),
            'message': "\n".join(messages),
            'type': 'warning',
            'sticky': False,
            # the form shows the approval it waits for at once
            'next': action or {'type': 'ir.actions.client', 'tag': 'soft_reload'},
        }
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': params}
