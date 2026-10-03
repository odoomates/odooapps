# Server side blocking of action buttons, reports and server actions by id.
# /web/action/load runs under sudo() with no access check, so it is done here.
import logging

from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.action import Action

_logger = logging.getLogger(__name__)


class ActionAccess(Action):

    @staticmethod
    def _resolve_action_id(action_id):
        """ Mirror the resolution /web/action/load does, without raising. """
        try:
            return int(action_id)
        except (TypeError, ValueError):
            pass
        if not isinstance(action_id, str):
            return None
        if '.' in action_id:
            record = request.env.ref(action_id, raise_if_not_found=False)
            if record and record._name.startswith('ir.actions.'):
                return record.id
            return None
        record = request.env['ir.actions.actions'].sudo().search(
            [('path', '=', action_id)], limit=1)
        return record.id or None

    @http.route()
    def load(self, action_id, context=None):
        request.env['om.access.profile']._check_action(self._resolve_action_id(action_id))
        result = super().load(action_id, context=context)
        # filtered here: the action is built under sudo, where this module steps aside
        return request.env['om.access.profile']._filter_action_views(result)

    @http.route()
    def run(self, action_id, context=None):
        request.env['om.access.profile']._check_action(self._resolve_action_id(action_id))
        return super().run(action_id, context=context)
