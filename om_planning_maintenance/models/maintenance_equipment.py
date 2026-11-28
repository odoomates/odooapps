from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    resource_id = fields.Many2one(
        'resource.resource', string="Planning Resource", copy=False, index='btree_not_null',
        ondelete='set null', readonly=True,
        help="Resource of the equipment in the planning, created automatically.")
    planning_role_ids = fields.Many2many(
        related='resource_id.planning_role_ids', readonly=False, string="Planning Roles")
    planning_slot_count = fields.Integer(compute='_compute_planning_slot_count', string="Bookings")

    def _compute_planning_slot_count(self):
        counts = dict(self.env['om.planning.slot'].sudo()._read_group(
            [('resource_ids', 'in', self.resource_id.ids)], ['resource_ids'], ['__count']))
        for equipment in self:
            equipment.planning_slot_count = counts.get(equipment.resource_id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        equipment = super().create(vals_list)
        equipment._planning_ensure_resource()
        return equipment

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'active', 'company_id'} & set(vals):
            for equipment in self.filtered('resource_id'):
                equipment.resource_id.sudo().write(equipment._planning_resource_values(update=True))
        return res

    def _planning_resource_values(self, update=False):
        self.ensure_one()
        values = {
            'name': self.name,
            'active': self.active,
            'company_id': self.company_id.id,
        }
        if not update:
            values.update({
                'resource_type': 'material',
                # equipment is available around the clock unless a working schedule is set
                'calendar_id': self.env['resource.resource']._planning_around_the_clock_calendar().id,
                'maintenance_equipment_id': self.id,
            })
        return values

    def _planning_ensure_resource(self):
        """ Create the planning resource of the equipment that has none (linked both ways). """
        Resource = self.env['resource.resource'].sudo().with_context(active_test=False)
        for equipment in self.sudo().with_context(active_test=False).filtered(lambda e: not e.resource_id):
            resource = Resource.search([('maintenance_equipment_id', '=', equipment.id)], limit=1)
            if not resource:
                resource = Resource.create(equipment._planning_resource_values())
            equipment.resource_id = resource

    def action_view_planning(self):
        self.ensure_one()
        self._planning_ensure_resource()
        action = self.resource_id.sudo().action_view_planning()
        action['name'] = self.env._("Bookings: %s", self.display_name)
        return action
