from odoo import api, fields, models
from odoo.fields import Command, Domain


class OmPlanningSlot(models.Model):
    _inherit = 'om.planning.slot'

    material_resource_ids = fields.Many2many(
        'resource.resource', 'om_planning_slot_material_rel', 'slot_id', 'resource_id',
        compute='_compute_material_resource_ids', store=True, readonly=False, string="Assets",
        group_expand='_group_expand_material_resource_ids',
        help="Equipment, vehicles and other material resources of the slot.")
    maintenance_request_id = fields.Many2one(
        'maintenance.request', compute='_compute_maintenance_request_id', store=True,
        index='btree_not_null', string="Maintenance Request")

    @api.depends('resource_ids', 'resource_ids.resource_type')
    def _compute_material_resource_ids(self):
        for slot in self:
            slot.material_resource_ids = slot.resource_ids.filtered(lambda r: r.resource_type == 'material')

    @api.depends('source_ref')
    def _compute_maintenance_request_id(self):
        for slot in self:
            record = slot.source_ref
            slot.maintenance_request_id = record.id if record and record._name == 'maintenance.request' else False

    def _group_expand_material_resource_ids(self, resources, domain):
        """ Rows of the equipment schedules: the material resources of the context domain
        (``om_planning_material_rows``), also without booking in the period. """
        rows_domain = self.env.context.get('om_planning_material_rows')
        if not rows_domain or self._planning_expand_filtered(domain, ('resource_ids', 'id')):
            return resources
        others = self.env['resource.resource'].search(Domain.AND([
            Domain(rows_domain),
            Domain([('resource_type', '=', 'material'), ('company_id', 'in', self.env.companies.ids + [False])]),
        ]))
        return resources | others

    # ------------------------------------------------------------------
    # Equipment rows write the resources of the slot
    # ------------------------------------------------------------------

    @api.model
    def _planning_material_to_resources(self, vals, slot=None):
        """ Values on ``material_resource_ids`` (rows of the equipment schedules) become values on
        ``resource_ids``: the people of the slot are kept, its material resources replaced. """
        if 'material_resource_ids' not in vals:
            return vals
        vals = dict(vals)
        commands = vals.pop('material_resource_ids')
        if 'resource_ids' in vals:
            return vals
        current = slot.material_resource_ids if slot else self.env['resource.resource']
        new_ids = set(current.ids)
        for command in commands or []:
            if isinstance(command, int):
                new_ids.add(command)
            elif command[0] == Command.SET:
                new_ids = set(command[2])
            elif command[0] == Command.LINK:
                new_ids.add(command[1])
            elif command[0] in (Command.UNLINK, Command.DELETE):
                new_ids.discard(command[1])
            elif command[0] == Command.CLEAR:
                new_ids = set()
        people = slot.resource_ids.filtered(lambda r: r.resource_type != 'material') if slot \
            else self.env['resource.resource']
        vals['resource_ids'] = [Command.set(people.ids + sorted(new_ids))]
        return vals

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        materials = self.env.context.get('default_material_resource_ids')
        if materials and 'resource_ids' in fields and not res.get('resource_ids'):
            res['resource_ids'] = [Command.set(self._ids_from_commands(materials))]
        return res

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._planning_material_to_resources(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if 'material_resource_ids' in vals:
            if len(self) > 1:
                for slot in self:
                    slot.write(vals)
                return True
            vals = self._planning_material_to_resources(vals, slot=self)
        requests = self.maintenance_request_id
        res = super().write(vals)
        if requests and {'start_datetime', 'end_datetime', 'resource_ids'} & set(vals) \
                and not self.env.context.get('om_planning_mnt_no_sync'):
            self._planning_mnt_sync_requests()
        return res

    def _planning_mnt_sync_requests(self):
        """ A maintenance slot moved on the Gantt moves its request (dates, equipment, technicians). """
        for slot in self.filtered('maintenance_request_id'):
            request = slot.maintenance_request_id.sudo()
            values = {
                'schedule_date': slot.start_datetime,
                'schedule_end': slot.end_datetime,
            }
            equipment = slot.resource_ids.maintenance_equipment_id[:1]
            if equipment and equipment != request.equipment_id:
                values['equipment_id'] = equipment.id
            company = request.company_id or self.env.company
            if company.planning_mnt_plan_technicians:
                users = slot.resource_ids.filtered(lambda r: r.resource_type == 'user').user_id
                if set(users.ids) != set(request.user_ids.ids):
                    values['user_ids'] = [Command.set(users.ids)]
            request.with_context(om_planning_mnt_no_sync=True).write(values)

    @api.model
    def get_gantt_data(self, domain, groupby, read_specification, order=None, limit=None,
                       gantt_range=None, unavailability=False, progress_bar_fields=None):
        """ Equipment schedules only show the rows of their material resources (a slot of an
        equipment with a vehicle does not add a vehicle row). """
        result = super().get_gantt_data(
            domain, groupby, read_specification, order=order, limit=limit, gantt_range=gantt_range,
            unavailability=unavailability, progress_bar_fields=progress_bar_fields)
        rows_domain = self.env.context.get('om_planning_material_rows')
        if rows_domain and groupby and groupby[0] == 'material_resource_ids':
            allowed = set(self.env['resource.resource'].with_context(active_test=False).search(rows_domain).ids)

            def keep(group):
                value = group.get('material_resource_ids')
                return not value or value[0] in allowed

            result['groups'] = [group for group in result['groups'] if keep(group)]
        return result

    @api.model
    def _gantt_progress_bar(self, field, res_ids, start, stop):
        if field == 'material_resource_ids':
            field = 'resource_ids'
        return super()._gantt_progress_bar(field, res_ids, start, stop)
