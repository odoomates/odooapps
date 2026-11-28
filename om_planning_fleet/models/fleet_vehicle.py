from odoo import api, fields, models
from odoo.fields import Command


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    resource_id = fields.Many2one(
        'resource.resource', string="Planning Resource", copy=False, index='btree_not_null',
        ondelete='set null', readonly=True,
        help="Resource of the vehicle in the planning, created automatically.")
    planning_follow_driver = fields.Boolean(
        string="Follows the Driver", default=lambda self: self.env.company.planning_fleet_follow_driver,
        help="The vehicle is added to the planning slots of its driver.")
    planning_driver_resource_id = fields.Many2one(
        related='resource_id.assigned_resource_id', string="Planned with")
    planning_slot_count = fields.Integer(compute='_compute_planning_slot_count', string="Bookings")

    def _compute_planning_slot_count(self):
        counts = dict(self.env['om.planning.slot'].sudo()._read_group(
            [('resource_ids', 'in', self.resource_id.ids)], ['resource_ids'], ['__count']))
        for vehicle in self:
            vehicle.planning_slot_count = counts.get(vehicle.resource_id, 0)

    @api.depends('model_id.brand_id.name', 'model_id.name', 'license_plate')
    def _compute_vehicle_name(self):
        super()._compute_vehicle_name()
        for vehicle in self.filtered(lambda v: v.resource_id and v.name and v.resource_id.name != v.name):
            vehicle.resource_id.sudo().name = vehicle.name

    @api.model_create_multi
    def create(self, vals_list):
        vehicles = super().create(vals_list)
        vehicles._planning_ensure_resource()
        vehicles._planning_fleet_follow_driver()
        return vehicles

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'active', 'company_id', 'model_id', 'license_plate'} & set(vals):
            for vehicle in self.filtered('resource_id'):
                vehicle.resource_id.sudo().write(vehicle._planning_resource_values(update=True))
        if {'driver_id', 'planning_follow_driver', 'active', 'company_id'} & set(vals):
            self._planning_fleet_follow_driver()
        return res

    def _planning_resource_values(self, update=False):
        self.ensure_one()
        values = {
            'name': self.name or self.license_plate or self.env._("Vehicle"),
            'active': self.active,
            'company_id': self.company_id.id,
        }
        if not update:
            values.update({
                'resource_type': 'material',
                # vehicles are available around the clock unless a working schedule is set
                'calendar_id': self.env['resource.resource']._planning_around_the_clock_calendar().id,
                'fleet_vehicle_id': self.id,
            })
        return values

    def _planning_ensure_resource(self):
        """ Create the planning resource of the vehicles that have none (linked both ways). """
        Resource = self.env['resource.resource'].sudo().with_context(active_test=False)
        for vehicle in self.sudo().with_context(active_test=False).filtered(lambda v: not v.resource_id):
            resource = Resource.search([('fleet_vehicle_id', '=', vehicle.id)], limit=1)
            if not resource:
                resource = Resource.create(vehicle._planning_resource_values())
            vehicle.resource_id = resource

    def _planning_fleet_follow_driver(self):
        """ The vehicle follows the planning resource of its driver: it is added to the coming
        slots of the driver (and taken out of the coming slots of the previous driver). """
        now = fields.Datetime.now()
        Slot = self.env['om.planning.slot'].sudo().with_context(
            om_planning_keep_published=True, om_planning_no_follower_sync=True, recurrence_update='this')
        for vehicle in self.sudo():
            resource = vehicle.resource_id
            if not resource:
                continue
            driver = self.env['resource.resource']
            if vehicle.active and vehicle.planning_follow_driver and vehicle.driver_id:
                driver = self.env['resource.resource']._planning_fleet_partner_resource(
                    vehicle.driver_id, vehicle.company_id or self.env.company)
            previous = resource.assigned_resource_id
            if previous == driver:
                continue
            resource.assigned_resource_id = driver
            if previous:
                old_slots = Slot.search([
                    ('resource_ids', 'in', previous.ids), ('resource_ids', 'in', resource.ids),
                    ('start_datetime', '>=', now),
                ])
                old_slots.write({'resource_ids': [Command.unlink(resource.id)]})
            if driver:
                new_slots = Slot.search([
                    ('resource_ids', 'in', driver.ids), ('resource_ids', 'not in', resource.ids),
                    ('start_datetime', '>=', now),
                ])
                company_slots = new_slots.filtered(
                    lambda s: not resource.company_id or s.company_id == resource.company_id)
                company_slots.write({'resource_ids': [Command.link(resource.id)]})

    def action_view_planning(self):
        self.ensure_one()
        self._planning_ensure_resource()
        action = self.resource_id.sudo().action_view_planning()
        action['name'] = self.env._("Bookings: %s", self.display_name)
        return action

    @api.model
    def _planning_fleet_demo(self):
        """ Demo data: a booking of a pool car and a day of work of the driver of a car. """
        vehicles = self.search([])
        vehicles._planning_ensure_resource()
        vehicles._planning_fleet_follow_driver()
        tz_name = self.env.ref('base.user_admin').tz or 'UTC'
        Slot = self.env['om.planning.slot']
        today = fields.Date.context_today(self)
        values_list = []
        pool_car = self.env.ref('fleet.vehicle_2', raise_if_not_found=False)
        if pool_car and pool_car.resource_id:
            pool_car.planning_follow_driver = False
            start = Slot._planning_fleet_local(today, 1, 9, tz_name)
            values_list.append({
                'name': self.env._("Customer visit"),
                'resource_ids': [Command.set(pool_car.resource_id.ids)],
                'start_datetime': start,
                'end_datetime': Slot._planning_fleet_local(today, 1, 13, tz_name),
            })
        car = self.env.ref('fleet.vehicle_1', raise_if_not_found=False)
        driver = car and car.resource_id.assigned_resource_id
        if driver:
            role = self.env.ref('om_planning.role_driver', raise_if_not_found=False)
            for day in (1, 2):
                values_list.append({
                    'resource_ids': [Command.set(driver.ids)],
                    'role_id': role.id if role else False,
                    'start_datetime': Slot._planning_fleet_local(today, day, 8, tz_name),
                    'end_datetime': Slot._planning_fleet_local(today, day, 16, tz_name),
                    'state': 'published',
                })
        Slot.create(values_list)
