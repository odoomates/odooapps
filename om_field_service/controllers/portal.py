from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class FieldServicePortal(CustomerPortal):

    def _fs_portal_domain(self):
        partner = request.env.user.partner_id.commercial_partner_id
        return [
            ('is_field_service', '=', True),
            ('partner_id', 'child_of', partner.id),
            ('job_state', '!=', 'cancelled'),
        ]

    def _prepare_portal_counter_values(self, counter):
        if counter == 'fs_job_count':
            return 'project.task', self._fs_portal_domain(), 'sudo'
        return super()._prepare_portal_counter_values(counter)

    def _fs_portal_job(self, job_id):
        return request.env['project.task'].sudo().search(
            self._fs_portal_domain() + [('id', '=', job_id)], limit=1)

    @http.route(['/my/field_service'], type='http', auth='user', website=True)
    def portal_my_field_service(self, **kwargs):
        jobs = request.env['project.task'].sudo().search(
            self._fs_portal_domain(), order='planned_start desc, id desc', limit=200)
        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'field_service',
            'jobs': jobs,
        })
        return request.render('om_field_service.portal_my_field_service', values)

    @http.route(['/my/field_service/<int:job_id>'], type='http', auth='user', website=True)
    def portal_my_field_service_job(self, job_id, **kwargs):
        job = self._fs_portal_job(job_id)
        if not job:
            return request.redirect('/my/field_service')
        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'field_service_job',
            'job': job,
        })
        return request.render('om_field_service.portal_my_field_service_job', values)

    @http.route(['/my/field_service/<int:job_id>/report'], type='http', auth='user', website=True)
    def portal_my_field_service_report(self, job_id, download=False, **kwargs):
        job = self._fs_portal_job(job_id)
        if not job or job.job_state != 'done':
            return request.redirect('/my/field_service')
        return self._show_report(model=job, report_type='pdf', report_ref='om_field_service.action_report_fs_job',
                                 download=download)
