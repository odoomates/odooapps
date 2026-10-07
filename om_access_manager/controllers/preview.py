# Ending a preview (see models/om_access_preview.py).
from odoo import http
from odoo.http import request


class AccessPreview(http.Controller):

    @http.route('/om_access_manager/preview/stop', type='json', auth='user')
    def stop(self):
        data = request.env['res.users']._om_preview_stop()
        if data and data.get('cids'):
            # the web client moved the company cookie to the previewed user's companies
            request.future_response.set_cookie('cids', data['cids'])
        return {'url': (data or {}).get('back') or '/web'}
