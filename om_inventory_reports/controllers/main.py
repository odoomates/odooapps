import json
import logging

from odoo import http
from odoo.http import request
from odoo.http.dispatcher import serialize_exception
from odoo.http.stream import content_disposition
from odoo.tools.misc import html_escape

_logger = logging.getLogger(__name__)


class OmInventoryReportController(http.Controller):

    @http.route('/om_inventory_reports/export', type='http', auth='user', methods=['POST'])
    def export(self, data, **kwargs):
        """The report as a file, the way it is shown: same options, the same
        lines unfolded (or all of them)."""
        try:
            params = json.loads(data)
            content, filename, mimetype = request.env['om.inventory.report.export']._om_render_file(params)
            return request.make_response(content, headers=[
                ('Content-Type', mimetype),
                ('Content-Length', len(content)),
                ('Content-Disposition', content_disposition(filename)),
            ])
        except Exception as error:  # noqa: BLE001 - shown to the user by the download helper
            _logger.warning("Inventory report export failed", exc_info=True)
            payload = {'code': 200, 'message': 'Odoo Server Error', 'data': serialize_exception(error)}
            return request.make_response(html_escape(json.dumps(payload)))
