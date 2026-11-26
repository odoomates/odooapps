import uuid
from collections import defaultdict
from datetime import UTC, datetime

from odoo import api, fields, models
from odoo.tools.date_utils import localized, sum_intervals
from odoo.tools.intervals import Intervals


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    planning_role_ids = fields.Many2many(
        'om.planning.role', 'om_planning_role_resource_rel', 'resource_id', 'role_id',
        string="Planning Roles")
    planning_default_role_id = fields.Many2one(
        'om.planning.role', string="Default Role",
        help="Role proposed on the new slots of this resource.")
    assigned_resource_id = fields.Many2one(
        'resource.resource', string="Follows",
        domain="[('resource_type', '=', 'user'), ('id', '!=', id)]",
        help="A tool or vehicle that goes with this person: it is added to the slots of the person.")
    following_resource_ids = fields.One2many(
        'resource.resource', 'assigned_resource_id', string="Assigned Equipment")
    planning_capacity = fields.Integer(
        string="Capacity", default=1,
        help="Number of slots this resource can take at the same time (a pool of identical units).")
    planning_image = fields.Image(string="Picture", max_width=256, max_height=256)
    planning_avatar_128 = fields.Image(compute='_compute_planning_avatar_128', string="Planning Avatar")
    planning_note = fields.Text(string="Planning Notes")
    planning_token = fields.Char(copy=False, groups='om_planning.group_planning_manager')
    planning_slot_count = fields.Integer(compute='_compute_planning_slot_count', string="Slots")

    _check_planning_capacity = models.Constraint(
        'CHECK(planning_capacity > 0)',
        'The capacity of a resource must be at least 1.',
    )

    @api.depends('planning_image', 'avatar_128')
    def _compute_planning_avatar_128(self):
        for resource in self:
            resource.planning_avatar_128 = resource.planning_image or resource.avatar_128

    def _compute_planning_slot_count(self):
        counts = dict(self.env['om.planning.slot']._read_group(
            [('resource_ids', 'in', self.ids)], ['resource_ids'], ['__count']))
        for resource in self:
            resource.planning_slot_count = counts.get(resource, 0)

    @api.onchange('planning_role_ids')
    def _onchange_planning_role_ids(self):
        if self.planning_default_role_id not in self.planning_role_ids._origin:
            self.planning_default_role_id = self.planning_role_ids[:1]._origin

    def action_view_planning(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_planning.action_om_planning_slot')
        action['domain'] = [('resource_ids', 'in', self.ids)]
        action['context'] = {'default_resource_ids': self.ids}
        return action

    # ------------------------------------------------------------------
    # Engine
    # ------------------------------------------------------------------

    @api.model
    def _planning_utc(self, dt):
        """ Aware UTC datetime from a naive UTC or an aware datetime. """
        if isinstance(dt, datetime) and dt.tzinfo:
            return dt.astimezone(UTC)
        return localized(fields.Datetime.to_datetime(dt)).astimezone(UTC)

    def _planning_get_partner(self):
        """ Contact that receives the schedule of the resource (empty for equipment). """
        self.ensure_one()
        return self.user_id.partner_id

    def _planning_get_access_token(self):
        self.ensure_one()
        resource = self.sudo()
        if not resource.planning_token:
            resource.planning_token = uuid.uuid4().hex
        return resource.planning_token

    def _planning_work_intervals(self, start, stop, compute_leaves=True):
        """ Working periods of the resources (working schedule, leaves removed by default).

        :return: ``{resource_id: Intervals}`` with aware UTC datetimes
        """
        start, stop = self._planning_utc(start), self._planning_utc(stop)
        if not self:
            return {}
        work, _calendar_work = self._get_valid_work_intervals(start, stop, compute_leaves=compute_leaves)
        return {
            resource.id: Intervals([
                (s.astimezone(UTC), e.astimezone(UTC), recs) for s, e, recs in work.get(resource.id, [])
            ])
            for resource in self
        }

    def _planning_leave_intervals(self, start, stop):
        """ Leaves of the resources and public holidays of their working schedule.

        :return: ``{resource_id: Intervals}`` with aware UTC datetimes, the records of each
            interval are the ``resource.calendar.leaves``
        """
        start, stop = self._planning_utc(start), self._planning_utc(stop)
        result = {resource.id: Intervals() for resource in self}
        for calendar, resources in self.grouped('calendar_id').items():
            leaves = calendar._leave_intervals_batch(
                start, stop, resources_per_tz=resources._get_resources_per_tz())
            for resource in resources:
                result[resource.id] = Intervals([
                    (s.astimezone(UTC), e.astimezone(UTC), recs)
                    for s, e, recs in leaves.get(resource.id, [])
                ])
        return result

    def _planning_booked_slots(self, start, stop, exclude_slots=None):
        """ Slots of the resources overlapping the period, drafts included. """
        domain = [
            ('resource_ids', 'in', self.ids),
            ('start_datetime', '<', fields.Datetime.to_string(self._planning_utc(stop).replace(tzinfo=None))),
            ('end_datetime', '>', fields.Datetime.to_string(self._planning_utc(start).replace(tzinfo=None))),
        ]
        if exclude_slots:
            domain.append(('id', 'not in', exclude_slots.ids))
        return self.env['om.planning.slot'].sudo().search(domain)

    def _planning_full_intervals(self, start, stop, exclude_slots=None):
        """ Periods where the resources are booked up to their capacity.

        :return: ``{resource_id: Intervals}`` with aware UTC datetimes, the records of each
            interval are the slots
        """
        slots = self._planning_booked_slots(start, stop, exclude_slots)
        per_resource = defaultdict(list)
        for slot in slots:
            for resource in slot.resource_ids & self:
                per_resource[resource.id].append(slot)
        result = {}
        for resource in self:
            capacity = max(resource.planning_capacity, 1)
            bounds = []
            for slot in per_resource[resource.id]:
                bounds.append((self._planning_utc(slot.start_datetime), 1, slot))
                bounds.append((self._planning_utc(slot.end_datetime), -1, slot))
            bounds.sort(key=lambda b: (b[0], b[1]))
            full, count, opened, running = [], 0, None, self.env['om.planning.slot']
            for moment, step, slot in bounds:
                running = running | slot if step > 0 else running - slot
                count += step
                if count >= capacity and opened is None:
                    opened = moment
                elif count < capacity and opened is not None:
                    if moment > opened:
                        full.append((opened, moment, running | slot))
                    opened = None
            result[resource.id] = Intervals(full)
        return result

    def _planning_free_intervals(self, start, stop, exclude_slots=None):
        """ Free time of the resources: working time minus leaves minus booked slots
        (for a pool, the periods where all its units are booked).

        :param datetime start: start (naive UTC or aware)
        :param datetime stop: end (naive UTC or aware)
        :param exclude_slots: slots to ignore (e.g. the slot being moved)
        :return: ``{resource_id: Intervals}`` with aware UTC datetimes
        """
        work = self._planning_work_intervals(start, stop)
        full = self._planning_full_intervals(start, stop, exclude_slots)
        return {resource.id: work[resource.id] - full[resource.id] for resource in self}

    def _planning_capacity_hours(self, start, stop):
        """ Working hours of the resources in the period (leaves removed), times their capacity.

        :return: ``{resource_id: hours}``
        """
        work = self._planning_work_intervals(start, stop)
        return {
            resource.id: round(sum_intervals(work[resource.id]) * max(resource.planning_capacity, 1), 2)
            for resource in self
        }

    def _planning_booked_hours(self, start, stop):
        """ Allocated hours of the slots of the resources in the period (prorated at the bounds).

        :return: ``{resource_id: hours}``
        """
        start, stop = self._planning_utc(start), self._planning_utc(stop)
        result = defaultdict(float)
        for slot in self._planning_booked_slots(start, stop):
            hours = slot._planning_hours_between(start, stop)
            for resource in slot.resource_ids & self:
                result[resource.id] += hours
        return dict(result)
