from odoo import api, fields, models
from odoo.fields import Command

# request fields that change its planning slot
SLOT_FIELDS = {'name', 'schedule_date', 'schedule_end', 'equipment_id', 'user_ids', 'state',
               'company_id', 'maintenance_team_id'}


class MaintenanceRequest(models.Model):
    _name = 'maintenance.request'
    _inherit = ['maintenance.request', 'om.planning.source']

    planning_conflict_info = fields.Text(compute='_compute_planning_conflict_info', string="Planning Conflicts")

    @api.depends('schedule_date', 'schedule_end', 'equipment_id', 'user_ids')
    def _compute_planning_conflict_info(self):
        for request in self:
            slots = request._origin._planning_mnt_slots() if request._origin.id else self.env['om.planning.slot']
            request.planning_conflict_info = '\n'.join(filter(None, slots.mapped('conflict_info'))) or False

    def _planning_hours_to_plan(self):
        self.ensure_one()
        return self.duration or 0.0

    def _planning_role(self):
        self.ensure_one()
        return self.env.ref('om_planning_maintenance.planning_role_maintenance', raise_if_not_found=False) \
            or super()._planning_role()

    def _planning_slot_values(self):
        values = super()._planning_slot_values()
        values['name'] = self._planning_mnt_slot_name()
        if self.equipment_id:
            self.equipment_id._planning_ensure_resource()
        resources = self._planning_mnt_resources()
        if resources:
            values['resource_ids'] = [Command.set(resources.ids)]
        return values

    def _planning_mnt_slot_name(self):
        self.ensure_one()
        if self.equipment_id:
            return f'{self.name} - {self.equipment_id.name}'
        return self.name

    def _planning_mnt_resources(self):
        """ Resources booked by the request: its equipment and, with the company setting, its
        technicians. """
        self.ensure_one()
        resources = self.equipment_id.sudo().resource_id.filtered('active')
        company = self.company_id or self.env.company
        if company.planning_mnt_plan_technicians and self.user_ids:
            resources |= self.env['resource.resource']._planning_mnt_user_resources(self.user_ids, company)
        return resources

    def _planning_mnt_slots(self):
        return self.env['om.planning.slot'].sudo().search(
            [('source_ref', 'in', self._planning_source_refs())])

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        if not self.env.context.get('om_planning_mnt_no_sync'):
            requests._planning_mnt_sync_slots()
        return requests

    def write(self, vals):
        res = super().write(vals)
        if SLOT_FIELDS & set(vals) and not self.env.context.get('om_planning_mnt_no_sync'):
            self._planning_mnt_sync_slots()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_planning_mnt_slots(self):
        self._planning_mnt_slots().unlink()

    def _planning_mnt_sync_slots(self):
        """ The planning slot of a scheduled request books its equipment (and technicians) from
        the scheduled date to the scheduled end. A cancelled request frees them, a request done
        early frees them from the moment it is done. """
        Slot = self.env['om.planning.slot'].sudo().with_context(
            om_planning_mnt_no_sync=True, om_planning_keep_published=True, recurrence_update='this')
        now = fields.Datetime.now()
        for request in self:
            slots = request._planning_mnt_slots().with_context(Slot.env.context)
            if request.state == 'cancelled' or not (request.schedule_date and request.schedule_end) \
                    or request.schedule_end <= request.schedule_date:
                slots.unlink()
                continue
            if request.state == 'done':
                # done: the equipment is free again from now when the work ended early
                for slot in slots:
                    if slot.start_datetime >= now:
                        slot.unlink()
                    elif slot.end_datetime > now:
                        slot.end_datetime = now
                continue
            resources = request._planning_mnt_resources()
            if not resources:
                slots.unlink()
                continue
            values = {
                'name': request._planning_mnt_slot_name(),
                'start_datetime': request.schedule_date,
                'end_datetime': request.schedule_end,
                'resource_ids': [Command.set(resources.ids)],
            }
            if request.company_id:
                values['company_id'] = request.company_id.id
            if len(slots) > 1:
                slots[1:].unlink()
                slots = slots[:1]
            if slots:
                slots.write(values)
            else:
                Slot.create({**request._planning_slot_values(), **values, 'state': 'published'})

    def action_plan(self):
        action = super().action_plan()
        action['context'] = dict(action['context'], search_default_group_resource=1)
        return action
