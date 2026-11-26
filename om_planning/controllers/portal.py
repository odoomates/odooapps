from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class PlanningPortal(CustomerPortal):

    def _planning_resources(self):
        return request.env['resource.resource'].sudo().search([('user_id', '=', request.env.uid)])

    def _prepare_portal_counter_values(self, counter):
        if counter == 'planning_slot_count':
            resources = self._planning_resources()
            return 'om.planning.slot', [
                ('resource_ids', 'in', resources.ids), ('state', '=', 'published'),
                ('end_datetime', '>=', fields.Datetime.now()),
            ], 'sudo'
        return super()._prepare_portal_counter_values(counter)

    @http.route(['/my/planning'], type='http', auth='user', website=True)
    def portal_my_planning(self, past=False, message=None, **kwargs):
        resources = self._planning_resources()
        Slot = request.env['om.planning.slot'].sudo()
        now = fields.Datetime.now()
        since = now - timedelta(days=30) if past else now - timedelta(hours=12)
        slots = Slot.search([
            ('resource_ids', 'in', resources.ids), ('state', '=', 'published'),
            ('end_datetime', '>=', since),
        ], limit=200) if resources else Slot
        roles = resources.planning_role_ids
        open_domain = [('is_open', '=', True), ('state', '=', 'published'), ('start_datetime', '>=', now),
                       ('company_id', 'in', resources.company_id.ids or [request.env.company.id])]
        if roles:
            open_domain += ['|', ('role_id', '=', False), ('role_id', 'in', roles.ids)]
        open_slots = Slot.search(open_domain, limit=100) if resources else Slot
        requests_ = request.env['om.planning.request'].sudo().search(
            [('resource_id', 'in', resources.ids)], limit=50) if resources else request.env['om.planning.request']
        values = self._prepare_portal_layout_values()
        resource = resources[:1]
        values.update({
            'page_name': 'planning',
            'resources': resources,
            'slots': slots,
            'open_slots': open_slots,
            'planning_requests': requests_,
            'pending_slots': requests_.filtered(lambda r: r.state == 'pending').slot_id,
            'ics_url': resource and '/planning/ics/%s.ics' % resource._planning_get_access_token(),
            'format_slot': lambda slot: request.env['om.planning.schedule'].sudo().planning_format_slot(
                slot, resource.id),
            'past': past,
            'message': message,
        })
        return request.render('om_planning.portal_my_planning', values)

    @http.route(['/my/planning/claim/<int:slot_id>', '/my/planning/leave/<int:slot_id>'],
                type='http', auth='user', methods=['POST'], website=True)
    def portal_my_planning_request(self, slot_id, reason=None, **kwargs):
        resources = self._planning_resources()
        slot = request.env['om.planning.slot'].sudo().browse(slot_id).exists()
        claim = request.httprequest.path.startswith('/my/planning/claim/')
        if not resources or not slot or slot.state != 'published':
            return request.redirect('/my/planning?message=unavailable')
        if claim:
            resource = resources[:1]
            valid = slot.is_open
        else:
            resource = (slot.resource_ids & resources)[:1]
            valid = bool(resource)
        if not valid:
            return request.redirect('/my/planning?message=unavailable')
        try:
            request.env['om.planning.request'].sudo().create({
                'slot_id': slot.id, 'resource_id': resource.id,
                'request_type': 'claim' if claim else 'unassign', 'reason': reason,
            })
        except UserError:
            return request.redirect('/my/planning?message=duplicate')
        return request.redirect('/my/planning?message=sent')
