from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.date_utils import sum_intervals
from odoo.tools.intervals import Intervals


class OmPlanningLoadWizard(models.TransientModel):
    _name = 'om.planning.load.wizard'
    _description = "Planned vs Capacity"

    date_from = fields.Date(string="From", required=True,
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string="To", required=True,
                          default=lambda self: (fields.Date.context_today(self).replace(day=1)
                                                + timedelta(days=32)).replace(day=1) - timedelta(days=1))
    resource_ids = fields.Many2many('resource.resource', string="Resources",
                                    help="Leave empty for every resource with a planning role.")

    def action_open(self):
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(self.env._("The end date must be after the start date."))
        Load = self.env['om.planning.load']
        Load.search([('create_uid', '=', self.env.uid)]).unlink()
        resources = self.resource_ids or self.env['resource.resource'].search(
            ['|', ('planning_role_ids', '!=', False), ('id', 'in',
                  self.env['om.planning.slot'].search([]).resource_ids.ids)])
        tz = ZoneInfo(self.env.user.tz or 'UTC')
        start = datetime.combine(self.date_from, datetime.min.time(), tzinfo=tz)
        stop = datetime.combine(self.date_to + timedelta(days=1), datetime.min.time(), tzinfo=tz)
        work = resources._planning_work_intervals(start, stop)
        slots = self.env['om.planning.slot'].search([
            ('start_datetime', '<', stop.astimezone(UTC).replace(tzinfo=None)),
            ('end_datetime', '>', start.astimezone(UTC).replace(tzinfo=None)),
        ])
        values_list = []
        days = (self.date_to - self.date_from).days + 1
        for day_index in range(days):
            day = self.date_from + timedelta(days=day_index)
            day_start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
            day_stop = day_start + timedelta(days=1)
            day_interval = Intervals([(day_start.astimezone(UTC), day_stop.astimezone(UTC), slots.browse())])
            for resource in resources:
                capacity = sum_intervals(work[resource.id] & day_interval) * max(resource.planning_capacity, 1)
                if capacity:
                    values_list.append({
                        'date': day, 'resource_id': resource.id,
                        'role_id': resource.planning_default_role_id.id,
                        'capacity_hours': round(capacity, 2),
                    })
            for slot in slots:
                hours = slot._planning_hours_between(day_start, day_stop)
                if not hours:
                    continue
                for resource in slot.resource_ids or [False]:
                    values_list.append({
                        'date': day, 'resource_id': resource.id if resource else False,
                        'role_id': slot.role_id.id, 'planned_hours': round(hours, 2),
                        'open_hours': round(hours, 2) if not resource else 0.0,
                    })
        Load.create(values_list)
        action = self.env['ir.actions.act_window']._for_xml_id('om_planning.action_om_planning_load')
        action['domain'] = [('create_uid', '=', self.env.uid)]
        return action


class OmPlanningLoad(models.Model):
    _name = 'om.planning.load'
    _description = "Planned vs Capacity Analysis"
    _order = 'date, resource_id'

    date = fields.Date(string="Date", required=True)
    resource_id = fields.Many2one('resource.resource', string="Resource", ondelete='cascade')
    role_id = fields.Many2one('om.planning.role', string="Role", ondelete='set null')
    capacity_hours = fields.Float(string="Capacity (h)", aggregator='sum')
    planned_hours = fields.Float(string="Planned (h)", aggregator='sum')
    open_hours = fields.Float(string="Open Slots (h)", aggregator='sum')
    free_hours = fields.Float(compute='_compute_free_hours', store=True, string="Free (h)", aggregator='sum')

    @api.depends('capacity_hours', 'planned_hours', 'open_hours')
    def _compute_free_hours(self):
        for line in self:
            line.free_hours = line.capacity_hours - (line.planned_hours - line.open_hours)
