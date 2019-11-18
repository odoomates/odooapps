from odoo import http
from odoo.http import request


class Hospital(http.Controller):

    # Sample Controller Created
    @http.route('/hospital/patient/', website=True, auth='user')
    def hospital_patient(self, **kw):
        # return "Thanks for watching"
        patients = request.env['hospital.patient'].sudo().search([])
        return request.render("om_hospital.patients_page", {
            'patients': patients
        })
