# The /json views run an action given in the URL: refuse the hidden ones.
from odoo.http import request

from odoo.addons.web.controllers.json import WebJsonController


class WebJsonAccess(WebJsonController):

    def _get_action(self, subpath):
        result = super()._get_action(subpath)
        action = result[0]
        request.env['om.access.profile']._check_action(action.id)
        return result
