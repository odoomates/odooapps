from odoo import http
from odoo.http import request

IMAGE_FIELDS = ('om_home_background', 'om_favicon')


class ThemeLiteImages(http.Controller):

    @http.route('/om_theme_lite/company/<int:company_id>/<string:field>',
                type='http', auth='public', readonly=True)
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
        return request.env['ir.binary']._get_image_stream_from(company, field).get_response(
            max_age=3600,
        )
