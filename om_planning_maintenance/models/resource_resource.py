from odoo import api, fields, models
from odoo.tools.intervals import Intervals


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    maintenance_equipment_id = fields.Many2one(
        'maintenance.equipment', string="Equipment", index='btree_not_null', ondelete='set null',
        help="Maintenance equipment planned with this resource.")

    _unique_maintenance_equipment = models.UniqueIndex(
        '(maintenance_equipment_id) WHERE maintenance_equipment_id IS NOT NULL',
        'An equipment has only one planning resource.',
    )

    def _planning_leave_intervals(self, start, stop):
        """ Equipment and other units with a fully flexible schedule are only unavailable
        on their own leaves (out of order, inspection), not on the public holidays of the company. """
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
    def _planning_mnt_user_resources(self, users, company):
        """ Planning resources of users (technicians): the resource of their employee or user,
        created when they have none. """
        Resource = self.sudo().with_context(active_test=False)
        result = Resource.browse()
        for user in users:
            resources = Resource.search([
                ('user_id', '=', user.id),
                ('resource_type', '=', 'user'),
                ('company_id', 'in', [company.id, False]),
            ], order='active desc, id')
            if 'employee_id' in Resource._fields:
                resources = resources.sorted(lambda r: (not r.employee_id, not r.active, r.id))
            resource = resources[:1]
            if resource and not resource.active:
                resource = Resource.browse()
            if not resource:
                resource = Resource.create({
                    'name': user.name,
                    'user_id': user.id,
                    'resource_type': 'user',
                    'company_id': company.id,
                    'calendar_id': company.resource_calendar_id.id,
                    'tz': user.tz or company.resource_calendar_id.tz or 'UTC',
                })
            result |= resource
        return result
