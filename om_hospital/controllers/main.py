from odoo import http


class Hospital(http.Controller):

    # Sample Controller Created
    @http.route('/hospital/doctor/', auth='public')
    def hospital_doctor(self, **kw):
        return "Hello, world"
