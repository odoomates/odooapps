from odoo import api, fields, models
from odoo.tools.intervals import Intervals


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle', string="Vehicle", index='btree_not_null', ondelete='set null',
        help="Vehicle planned with this resource.")

    _unique_fleet_vehicle = models.UniqueIndex(
        '(fleet_vehicle_id) WHERE fleet_vehicle_id IS NOT NULL',
        'A vehicle has only one planning resource.',
    )

    def _planning_leave_intervals(self, start, stop):
        """ Vehicles and other units with a fully flexible schedule are only unavailable
        on their own leaves (workshop, inspection), not on the public holidays of the company. """
        result = super()._planning_leave_intervals(start, stop)
        for resource in self.filtered(lambda r: r.resource_type == 'material' and r._is_fully_flexible()):
            result[resource.id] = Intervals([
                (s, e, recs) for s, e, recs in result.get(resource.id, [])
                if recs.filtered(lambda leave: leave.resource_id == resource)
            ])
        return result

    @api.model
    def _planning_around_the_clock_calendar(self):
        """ Shared working schedule without hours (fully flexible): units on it are available day
        and night. """
        Calendar = self.env['resource.calendar'].sudo()
        calendar = Calendar.search([
            ('calendar_type', '=', 'undefined'),
            ('hours_per_week', '=', 0),
            ('hours_per_day', '=', 0),
            ('company_id', '=', False),
        ], limit=1)
        if not calendar:
            calendar = Calendar.create({
                'name': self.env._("Around the Clock"),
                'calendar_type': 'undefined',
                'hours_per_week': 0,
                'hours_per_day': 0,
                'company_id': False,
            })
        return calendar

    @api.model
    def _planning_fleet_partner_resource(self, partner, company):
        """ Planning resource of a driver (a contact): the resource of their user or employee,
        created for an internal user without one. Empty for a contact without user nor employee. """
        if not partner:
            return self.browse()
        Resource = self.sudo()
        company_domain = [('company_id', 'in', [company.id, False])]
        users = partner.sudo().with_context(active_test=False).user_ids.filtered(lambda u: u.active)
        resource = Resource.search([
            ('user_id', 'in', users.ids), ('resource_type', '=', 'user'), *company_domain,
        ], limit=1) if users else Resource
        if not resource and 'hr.employee' in self.env:
            employee = self.env['hr.employee'].sudo().search([
                ('work_contact_id', '=', partner.id), *company_domain], limit=1)
            resource = employee.resource_id
        if not resource:
            user = users.filtered(lambda u: not u.share)[:1]
            if user:
                resource = Resource.create({
                    'name': user.name,
                    'user_id': user.id,
                    'resource_type': 'user',
                    'company_id': company.id,
                    'calendar_id': company.resource_calendar_id.id,
                    'tz': user.tz or company.resource_calendar_id.tz or 'UTC',
                })
        return resource
