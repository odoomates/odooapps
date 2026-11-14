from odoo import http
from odoo.http import request


class AdaptiveViews(http.Controller):

    @http.route('/om_adaptive_views/collect', type='jsonrpc', auth='user')
    def collect(self, events=None):
        """ Add the counts a web client batched up. Only counts arrive here, never values. """
        return request.env['om.usage.stat'].sudo()._om_record(events)
