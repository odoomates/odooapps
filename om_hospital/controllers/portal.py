# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class CustomerPortal(CustomerPortal):

    def _prepare_portal_layout_values(self):
        values = super(CustomerPortal, self)._prepare_portal_layout_values()
        values['appointment_count'] = request.env['hospital.appointment'].sudo().search_count([])
        return values

    @http.route(['/my/appointments'], type='http', auth="user", website=True)
    def portal_my_appointments(self, **kw):
        values = self._prepare_portal_layout_values()
        appointments = request.env['hospital.appointment'].sudo().search([])
        values.update({
            'appointments': appointments,
        })
        return request.render("om_hospital.portal_my_appointments", values)

