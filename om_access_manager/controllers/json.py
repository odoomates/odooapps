# The /json views read the action's model with a domain and group-bys from the
# URL: mark it for the field guard and refuse hidden actions.
from odoo.http import request

from odoo.addons.web.controllers.json import WebJsonController

from ..models.field_guard import mark_rpc_entry


class WebJsonAccess(WebJsonController):

    def _get_action(self, subpath):
        result = super()._get_action(subpath)
        action = result[0]
        request.env['om.access.profile']._check_action(action.id)
        mark_rpc_entry(action.res_model, '*')
        return result
