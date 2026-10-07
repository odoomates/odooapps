# Ending a preview (see models/om_access_preview.py).
from odoo import http
from odoo.http import request


class AccessPreview(http.Controller):

    @http.route('/om_access_manager/preview/stop', type='json', auth='user')
    def stop(self):
        data = request.env['res.users']._om_preview_stop()
        # the web client moved the company cookie to the previewed user's
        # companies: the banner puts it back (Odoo 15 sets no cookie on a JSON answer)
        return {'url': (data or {}).get('back') or '/web', 'cids': (data or {}).get('cids')}
