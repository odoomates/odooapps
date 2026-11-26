from datetime import timedelta

from odoo import fields, http
from odoo.http import request
from odoo.tools import consteq


class PlanningSchedule(http.Controller):

    def _get_schedule_resource(self, token, resource_token):
        schedule = request.env['om.planning.schedule'].sudo().search(
            [('access_token', '=', token), ('state', '=', 'sent')], limit=1)
        resource = self._get_resource(resource_token)
        if not schedule or not resource:
            return None, None
        return schedule, resource

    def _get_resource(self, resource_token):
        if not resource_token or len(resource_token) < 16:
            return None
        resource = request.env['resource.resource'].sudo().search(
            [('planning_token', '=', resource_token)], limit=1)
        if not resource or not consteq(resource.planning_token, resource_token):
            return None
        return resource

    @http.route('/planning/schedule/<string:token>/<string:resource_token>', type='http', auth='public',
                website=False, sitemap=False)
    def planning_schedule(self, token, resource_token, message=None, **kwargs):
        schedule, resource = self._get_schedule_resource(token, resource_token)
        if not schedule:
            return request.not_found()
        slots = schedule.planning_resource_slots(resource.id)
        open_slots = schedule.planning_open_slots(resource.id) if schedule.include_open_slots else schedule.slot_ids.browse()
        pending = request.env['om.planning.request'].sudo().search([
            ('resource_id', '=', resource.id), ('state', '=', 'pending'),
            ('slot_id', 'in', open_slots.ids),
        ]).slot_id
        return request.render('om_planning.planning_schedule_page', {
            'schedule': schedule,
            'resource': resource,
            'slots': slots,
            'open_slots': open_slots,
            'pending_slots': pending,
            'token': token,
            'resource_token': resource_token,
            'ics_url': schedule._get_ics_url(resource),
            'format_slot': lambda slot: schedule.planning_format_slot(slot, resource.id),
            'message': message,
        })

    @http.route('/planning/schedule/<string:token>/<string:resource_token>/claim/<int:slot_id>',
                type='http', auth='public', methods=['POST'], website=False, sitemap=False)
    def planning_schedule_claim(self, token, resource_token, slot_id, **kwargs):
        schedule, resource = self._get_schedule_resource(token, resource_token)
        if not schedule:
            return request.not_found()
        slot = schedule.planning_open_slots(resource.id).filtered(lambda s: s.id == slot_id)
        message = 'unavailable'
        if slot and slot.is_open:
            existing = request.env['om.planning.request'].sudo().search_count([
                ('slot_id', '=', slot.id), ('resource_id', '=', resource.id), ('state', '=', 'pending')])
            if not existing:
                request.env['om.planning.request'].sudo().create({
                    'slot_id': slot.id, 'resource_id': resource.id, 'request_type': 'claim',
                })
            message = 'claimed'
        return request.redirect(f'/planning/schedule/{token}/{resource_token}?message={message}')

    @http.route('/planning/ics/<string:resource_token>.ics', type='http', auth='public', sitemap=False)
    def planning_ics(self, resource_token, **kwargs):
        resource = self._get_resource(resource_token)
        if not resource:
            return request.not_found()
        since = fields.Datetime.now() - timedelta(days=60)
        slots = request.env['om.planning.slot'].sudo().search([
            ('resource_ids', 'in', resource.id),
            ('state', '=', 'published'),
            ('end_datetime', '>=', since),
        ])
        content = slots._planning_ics(resource.name)
        return request.make_response(content, headers=[
            ('Content-Type', 'text/calendar; charset=utf-8'),
            ('Content-Disposition', 'inline; filename="planning.ics"'),
        ])
