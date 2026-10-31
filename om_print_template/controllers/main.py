from odoo import http
from odoo.http import request


class PrintVerify(http.Controller):

    @http.route('/print/verify/<string:token>', type='http', auth='public', website=True, sitemap=False)
    def verify(self, token, **kwargs):
        """ The public page the QR code of a print opens: whether the print is genuine and still valid. """
        issue = request.env['print.issue'].sudo().search(
            [('access_token', '=', token), ('state', 'in', ('issued', 'cancelled'))], limit=1)
        if issue and not issue.show_qr:
            issue = issue.browse()
        return request.render('om_print_template.verify_page', {'issue': issue})
