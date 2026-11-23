from odoo.http import request, route

from odoo.addons.web.controllers.dataset import DataSet


class PenDataSet(DataSet):

    @route()
    def call_button(self, model, method, args, kwargs, path=None):
        """ A button that needs an approval shows the approval dialog instead of running. """
        ids = args[0] if args and isinstance(args[0], list) else []
        if ids and model in request.env and not method.startswith('_'):
            blocked = request.env['om.pen.approval.rule']._blocked_action(model, method, ids, 'object')
            if blocked:
                return blocked
        return super().call_button(model, method, args, kwargs, path=path)
