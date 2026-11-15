import base64

from odoo import http
from odoo.http import request

IMAGE_FIELDS = ('om_home_background', 'om_favicon')


class ThemeLiteImages(http.Controller):

    @http.route('/om_theme_lite/company/<int:company_id>/<string:field>',
                type='http', auth='public')
    def company_image(self, company_id, field, **kwargs):
        """Serve a company's theme images to anyone, the login page included.

        The login page is shown before anyone is signed in, so the images cannot go
        through /web/image, which checks read access on the company. Only the two
        theme images are served, nothing else of the company.
        """
        if field not in IMAGE_FIELDS:
            raise request.not_found()
        company = request.env['res.company'].sudo().browse(company_id).exists()
        if not company or not company[field]:
            raise request.not_found()
        status, headers, content = request.env['ir.http'].sudo().binary_content(
            model='res.company', id=company.id, field=field, default_mimetype='image/png')
        if status != 200:
            raise request.not_found()
        content = base64.b64decode(content)
        headers.append(('Content-Length', len(content)))
        headers.append(('Cache-Control', 'max-age=3600'))
        return request.make_response(content, headers)
