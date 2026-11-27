from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from odoo import http
from odoo.http import request
from odoo.tools import format_datetime

# status steps of the tracking page: job statuses of each step
STEPS = [
    ('planned', ('new', 'planned')),
    ('on_the_way', ('travelling',)),
    ('arrived', ('in_progress', 'waiting_parts')),
    ('done', ('done',)),
]


class FieldServiceTracking(http.Controller):

    def _fs_track_job(self, token):
        """ The job of a tracking link, while its page is open: not done, not cancelled. """
        if not token or len(token) < 20:
            return None, False
        job = request.env['project.task'].sudo().search([('fs_track_token', '=', token)], limit=1)
        if not job or not job._fs_company().fs_live_tracking:
            return None, False
        return job, job.job_state not in ('done', 'cancelled')

    def _fs_track_values(self, job):
        """ What the customer sees of the visit. The position only while on the way. """
        job = job.with_context(lang=job.partner_id.lang or request.env.lang)
        env = job.env
        tz = job.partner_id.tz or job.technician_ids[:1].resource_id.tz or 'UTC'
        step = next((key for key, states in STEPS if job.job_state in states), 'planned')
        technician = job.technician_ids[:1]
        site = job.site_partner_id or job.partner_id
        labels = {
            'planned': env._("Planned"),
            'on_the_way': env._("On the way"),
            'arrived': env._("Arrived"),
            'done': env._("Done"),
        }
        eta = job._fs_tracking_eta()
        eta_text = ''
        if eta:
            arrival = job.fs_track_date + timedelta(minutes=eta)
            arrival_time = arrival.replace(tzinfo=UTC).astimezone(ZoneInfo(tz)).strftime('%H:%M')
            eta_text = env._("About %(minutes)s min, around %(time)s", minutes=eta, time=arrival_time)
        elif step == 'planned' and job.planned_start:
            eta_text = env._("Visit planned on %s", format_datetime(env, job.planned_start, tz=tz))
        elif step == 'on_the_way':
            eta_text = env._("The arrival time shows as soon as the technician shares their position.")
        tracking = step == 'on_the_way' and bool(job.fs_track_date)
        return {
            'step': step,
            'steps': [{'key': key, 'label': labels[key]} for key, _states in STEPS],
            'status': labels[step],
            'technician': technician.name or '',
            'job': job.job_number or job.name,
            'name': job.name,
            'planned': format_datetime(env, job.planned_start, tz=tz) if job.planned_start else '',
            'eta': eta_text,
            'site': {'lat': site.partner_latitude, 'lng': site.partner_longitude}
            if site.partner_latitude or site.partner_longitude else False,
            'position': {'lat': job.fs_track_latitude, 'lng': job.fs_track_longitude} if tracking else False,
            'updated': format_datetime(env, job.fs_track_date, tz=tz, dt_format='HH:mm') if tracking else '',
            'company': job._fs_company().name,
        }

    @http.route(['/field-service/track/<string:token>'], type='http', auth='public', sitemap=False)
    def fs_track_page(self, token, **kwargs):
        job, live = self._fs_track_job(token)
        if not live:
            return request.render('om_field_service.fs_track_expired', {'job': job}, status=410 if job else 404)
        return request.render('om_field_service.fs_track_page', {
            'job': job,
            'token': token,
            'data': self._fs_track_values(job),
        })

    @http.route(['/field-service/track/<string:token>/data'], type='http', auth='public', sitemap=False)
    def fs_track_data(self, token, **kwargs):
        job, live = self._fs_track_job(token)
        if not live:
            return request.make_json_response({'expired': True})
        return request.make_json_response(self._fs_track_values(job))

    @http.route(['/field-service/track/<string:token>/photo'], type='http', auth='public', sitemap=False)
    def fs_track_photo(self, token, **kwargs):
        job, live = self._fs_track_job(token)
        technician = job.technician_ids[:1] if live else False
        if not technician:
            return request.not_found()
        return request.env['ir.binary']._get_image_stream_from(
            technician.sudo(), 'avatar_128').get_response(max_age=300)
