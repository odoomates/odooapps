from collections import defaultdict
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools.date_utils import sum_intervals
from odoo.tools.intervals import Intervals

# changes on these fields make a published slot "changed since published"
PUBLISHED_FIELDS = {'start_datetime', 'end_datetime', 'resource_ids', 'role_id', 'break_hours',
                    'allocated_percentage'}
# fields copied to the other slots of a series when editing "this and next" or "all"
RECURRENCE_FIELDS = {'resource_ids', 'role_id', 'break_hours', 'allocated_percentage', 'note', 'name',
                     'template_id', 'properties', 'source_ref'}
REPEAT_FIELDS = ('repeat', 'repeat_interval', 'repeat_unit', 'repeat_type', 'repeat_until', 'repeat_count')


class OmPlanningSlot(models.Model):
    _name = 'om.planning.slot'
    _description = "Planning Slot"
    _order = 'start_datetime, id'
    _check_company_auto = True

    name = fields.Char(string="Title")
    resource_ids = fields.Many2many(
        'resource.resource', 'om_planning_slot_resource_rel', 'slot_id', 'resource_id',
        string="Resources", check_company=True,
        help="People and equipment of the slot. A slot without resource is an open slot.",
        group_expand='_group_expand_resource_ids')
    resource_count = fields.Integer(compute='_compute_resource_count', string="Number of Resources")
    is_open = fields.Boolean(compute='_compute_is_open', store=True, string="Open Slot")
    role_id = fields.Many2one('om.planning.role', string="Role", index='btree_not_null',
                              group_expand='_group_expand_role_ids')
    template_id = fields.Many2one('om.planning.template', string="Template")
    color = fields.Integer(compute='_compute_color', store=True, readonly=False, string="Color")
    start_datetime = fields.Datetime(string="Start", required=True, index=True,
                                     default=lambda self: self._default_start())
    end_datetime = fields.Datetime(string="End", required=True, index=True,
                                   default=lambda self: self._default_end())
    break_hours = fields.Float(string="Break")
    allocated_percentage = fields.Float(string="Allocated Time (%)", default=100.0)
    duration_hours = fields.Float(compute='_compute_duration_hours', string="Duration")
    allocated_hours = fields.Float(
        compute='_compute_allocated_hours', store=True, string="Allocated Hours",
        help="Hours of work of each resource of the slot.")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
    ], string="Status", default='draft', required=True, index=True)
    changed_since_published = fields.Boolean(
        string="Changed Since Published", copy=False,
        help="The slot was changed after it was sent to the resources.")
    publication_date = fields.Datetime(string="Published On", copy=False, readonly=True)
    note = fields.Text(string="Notes")
    properties = fields.Properties('Properties', definition='role_id.slot_properties_definition', copy=True)
    company_id = fields.Many2one('res.company', string="Company", required=True, index=True,
                                 default=lambda self: self.env.company)
    source_ref = fields.Reference(
        selection='_selection_source_ref', string="Source", index='btree_not_null',
        help="Document the slot is planned for (an order, a task, a ticket...).")
    source_name = fields.Char(compute='_compute_source_name', store=True, string="Source Document")
    request_ids = fields.One2many('om.planning.request', 'slot_id', string="Requests")
    pending_request_count = fields.Integer(compute='_compute_pending_request_count', string="Pending Requests")
    is_mine = fields.Boolean(compute='_compute_is_mine', string="My Slot")

    # conflicts
    conflict_count = fields.Integer(compute='_compute_conflicts', string="Conflicts")
    conflict_info = fields.Text(compute='_compute_conflicts', string="Conflict Details")
    has_conflict = fields.Boolean(compute='_compute_conflicts', search='_search_has_conflict',
                                  string="Has Conflicts")

    # recurrence
    recurrence_id = fields.Many2one('om.planning.recurrence', string="Recurrence", copy=False,
                                    index='btree_not_null', ondelete='set null')
    repeat = fields.Boolean(compute='_compute_repeat', readonly=False, string="Repeat")
    repeat_interval = fields.Integer(compute='_compute_repeat', readonly=False, string="Repeat Every")
    repeat_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
    ], compute='_compute_repeat', readonly=False, string="Repeat Unit")
    repeat_type = fields.Selection([
        ('until', 'Until'),
        ('count', 'Number of Times'),
    ], compute='_compute_repeat', readonly=False, string="Repeat Type")
    repeat_until = fields.Date(compute='_compute_repeat', readonly=False, string="Repeat Until")
    repeat_count = fields.Integer(compute='_compute_repeat', readonly=False, string="Repetitions")
    recurrence_update = fields.Selection([
        ('this', 'This slot'),
        ('subsequent', 'This and following slots'),
        ('all', 'All slots'),
    ], string="Apply Changes To", store=False, default='this')

    _check_dates = models.Constraint(
        'CHECK(end_datetime > start_datetime)',
        'The end of a slot must be after its start.',
    )
    _check_percentage = models.Constraint(
        'CHECK(allocated_percentage >= 0)',
        'The allocated time cannot be negative.',
    )

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def _user_tz(self):
        return ZoneInfo(self.env.context.get('tz') or self.env.user.tz or 'UTC')

    def _default_start(self):
        tz = self._user_tz()
        today = datetime.now(tz).replace(hour=8, minute=0, second=0, microsecond=0)
        return today.astimezone(UTC).replace(tzinfo=None)

    def _default_end(self):
        tz = self._user_tz()
        today = datetime.now(tz).replace(hour=17, minute=0, second=0, microsecond=0)
        return today.astimezone(UTC).replace(tzinfo=None)

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if res.get('start_datetime') and res.get('end_datetime') and self.env.context.get('default_start_datetime'):
            res.update(self._adjust_cell_period(res['start_datetime'], res['end_datetime'], res))
        resource_ids = res.get('resource_ids') or self.env.context.get('default_resource_ids')
        if 'role_id' in fields and not res.get('role_id') and resource_ids:
            ids = self._ids_from_commands(resource_ids)
            role = self.env['resource.resource'].browse(ids[:1]).planning_default_role_id
            if role:
                res['role_id'] = role.id
        return res

    def _adjust_cell_period(self, start, stop, values):
        """ A slot created from a whole day of the Gantt takes the working hours of the day. """
        start, stop = fields.Datetime.to_datetime(start), fields.Datetime.to_datetime(stop)
        tz = self._user_tz()
        local_start = start.replace(tzinfo=UTC).astimezone(tz)
        local_stop = stop.replace(tzinfo=UTC).astimezone(tz)
        whole_days = local_start.time() == datetime.min.time() and (local_stop - local_start) >= timedelta(hours=23)
        if not whole_days:
            return {}
        role = self.env['om.planning.role'].browse(values.get('role_id') or self.env.context.get('default_role_id'))
        template = role.template_id
        if template:
            day_start, _dummy = template._get_period(local_start.date(), tz.key)
            last_day = (local_stop - timedelta(seconds=1)).date()
            _dummy, day_end = template._get_period(last_day, tz.key)
            return {'start_datetime': day_start, 'end_datetime': day_end,
                    'template_id': template.id, 'break_hours': template.break_hours}
        resource_ids = self._ids_from_commands(self.env.context.get('default_resource_ids'))
        resource = self.env['resource.resource'].browse(resource_ids[:1]).exists()
        calendar = resource.calendar_id or self.env.company.resource_calendar_id
        if not calendar:
            return {}
        work = calendar._work_intervals_batch(
            local_start, local_stop,
            resources_per_tz={ZoneInfo(resource.tz) if resource else tz: resource},
        )[resource.id]
        if not work:
            return {}
        items = list(work)
        return {
            'start_datetime': items[0][0].astimezone(UTC).replace(tzinfo=None),
            'end_datetime': items[-1][1].astimezone(UTC).replace(tzinfo=None),
        }

    @api.model
    def _planning_expand_filtered(self, domain, field_names):
        """ Whether the search filters on one of ``field_names`` (rows are not added then). """
        return any(
            condition.field_expr.split('.')[0] in field_names
            for condition in Domain(domain or []).iter_conditions()
        )

    @api.model
    def _planning_expand_resource_domain(self):
        """ Resources shown as Gantt rows even without slot in the period. """
        return Domain([
            ('planning_role_ids', '!=', False),
            ('company_id', 'in', self.env.companies.ids + [False]),
        ])

    def _group_expand_resource_ids(self, resources, domain):
        if self._planning_expand_filtered(domain, ('resource_ids', 'role_id', 'id', 'source_ref')):
            return resources
        others = self.env['resource.resource'].search(self._planning_expand_resource_domain())
        return resources | others

    def _group_expand_role_ids(self, roles, domain):
        if self._planning_expand_filtered(domain, ('resource_ids', 'role_id', 'id', 'source_ref')):
            return roles
        return roles | self.env['om.planning.role'].search(
            [('company_id', 'in', self.env.companies.ids + [False])])

    @api.model
    def _selection_source_ref(self):
        models_ = self.env['ir.model'].sudo().search([('transient', '=', False)])
        return [(model.model, model.name) for model in models_]

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('resource_ids')
    def _compute_resource_count(self):
        for slot in self:
            slot.resource_count = len(slot.resource_ids)

    @api.depends('resource_ids')
    def _compute_is_open(self):
        for slot in self:
            slot.is_open = not slot.resource_ids

    @api.depends('role_id.color', 'template_id.color')
    def _compute_color(self):
        for slot in self:
            slot.color = slot.template_id.color or slot.role_id.color or slot.color

    @api.depends('start_datetime', 'end_datetime')
    def _compute_duration_hours(self):
        for slot in self:
            if slot.start_datetime and slot.end_datetime:
                slot.duration_hours = (slot.end_datetime - slot.start_datetime).total_seconds() / 3600
            else:
                slot.duration_hours = 0.0

    @api.depends('start_datetime', 'end_datetime', 'break_hours', 'allocated_percentage', 'resource_ids')
    def _compute_allocated_hours(self):
        for slot in self:
            if not (slot.start_datetime and slot.end_datetime) or slot.end_datetime <= slot.start_datetime:
                slot.allocated_hours = 0.0
                continue
            duration = (slot.end_datetime - slot.start_datetime).total_seconds() / 3600
            if duration <= 24:
                hours = max(duration - slot.break_hours, 0.0)
            else:
                # several days: the working hours of the period
                resource = slot.resource_ids.filtered(lambda r: r.resource_type == 'user')[:1] or slot.resource_ids[:1]
                if resource:
                    hours = sum_intervals(resource._planning_work_intervals(
                        slot.start_datetime, slot.end_datetime)[resource.id])
                else:
                    calendar = slot.company_id.resource_calendar_id or self.env.company.resource_calendar_id
                    hours = calendar.get_work_hours_count(
                        slot.start_datetime.replace(tzinfo=UTC), slot.end_datetime.replace(tzinfo=UTC),
                        compute_leaves=False) if calendar else duration
            slot.allocated_hours = round(hours * slot.allocated_percentage / 100.0, 2)

    @api.depends('source_ref')
    def _compute_source_name(self):
        for slot in self:
            record = slot.source_ref
            slot.source_name = record.sudo().display_name if record else False

    def _compute_pending_request_count(self):
        counts = dict(self.env['om.planning.request'].sudo()._read_group(
            [('slot_id', 'in', self.ids), ('state', '=', 'pending')], ['slot_id'], ['__count']))
        for slot in self:
            slot.pending_request_count = counts.get(slot, 0)

    @api.depends('resource_ids.user_id')
    @api.depends_context('uid')
    def _compute_is_mine(self):
        for slot in self:
            slot.is_mine = self.env.user in slot.resource_ids.user_id

    @api.depends('recurrence_id')
    def _compute_repeat(self):
        for slot in self:
            recurrence = slot.recurrence_id
            slot.repeat = bool(recurrence)
            slot.repeat_interval = recurrence.repeat_interval or 1
            slot.repeat_unit = recurrence.repeat_unit or 'week'
            slot.repeat_type = recurrence.repeat_type or 'count'
            slot.repeat_until = recurrence.repeat_until
            slot.repeat_count = recurrence.repeat_count or 4

    @api.depends('start_datetime', 'end_datetime', 'resource_ids', 'role_id', 'allocated_hours')
    def _compute_conflicts(self):
        checks = self._planning_check()
        for slot in self:
            problems = checks.get(slot.id, [])
            slot.conflict_count = len(problems)
            slot.has_conflict = bool(problems)
            slot.conflict_info = '\n'.join(problem['message'] for problem in problems) or False

    def _search_has_conflict(self, operator, value):
        if operator not in ('in', 'not in'):
            return NotImplemented
        since = fields.Datetime.now() - timedelta(days=31)
        slots = self.search([('end_datetime', '>=', since), ('resource_ids', '!=', False)], limit=5000)
        conflict_ids = [slot_id for slot_id, problems in slots._planning_check().items() if problems]
        positive = True in value
        if operator == 'not in':
            positive = not positive
        return Domain('id', 'in' if positive else 'not in', conflict_ids)

    @api.depends('name', 'role_id', 'resource_ids')
    @api.depends_context('om_planning_label')
    def _compute_display_name(self):
        label = self.env.context.get('om_planning_label')
        for slot in self:
            who = ', '.join(slot.resource_ids.mapped('name')) or self.env._("Open slot")
            if label == 'role':
                name = slot.name or slot.role_id.name or who
            elif label == 'resource':
                name = who
            elif slot.name:
                name = slot.name
            else:
                name = f'{slot.role_id.name} - {who}' if slot.role_id else who
            slot.display_name = name

    def _planning_hours_between(self, start, stop):
        """ Allocated hours of the slot inside ``start`` - ``stop`` (aware or naive UTC). """
        self.ensure_one()
        to_utc = self.env['resource.resource']._planning_utc
        slot_start, slot_stop = to_utc(self.start_datetime), to_utc(self.end_datetime)
        start, stop = to_utc(start), to_utc(stop)
        total = (slot_stop - slot_start).total_seconds()
        inside = (min(stop, slot_stop) - max(start, slot_start)).total_seconds()
        if total <= 0 or inside <= 0:
            return 0.0
        return self.allocated_hours * inside / total

    # ------------------------------------------------------------------
    # Onchanges
    # ------------------------------------------------------------------

    @api.onchange('template_id')
    def _onchange_template_id(self):
        template = self.template_id
        if not template:
            return
        tz = self.resource_ids[:1].tz or self.env.context.get('tz') or self.env.user.tz or 'UTC'
        day = (self.start_datetime or fields.Datetime.now()).replace(tzinfo=UTC).astimezone(ZoneInfo(tz)).date()
        self.start_datetime, self.end_datetime = template._get_period(day, tz)
        self.break_hours = template.break_hours
        if template.role_id:
            self.role_id = template.role_id

    @api.onchange('role_id')
    def _onchange_role_id(self):
        if self.role_id.template_id and not self.template_id:
            self.template_id = self.role_id.template_id
            self._onchange_template_id()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        repeat_values = []
        for vals in vals_list:
            repeat_values.append({key: vals.pop(key) for key in REPEAT_FIELDS if key in vals})
            vals.pop('recurrence_update', None)
            if not vals.get('role_id') and vals.get('resource_ids'):
                resource_ids = self._ids_from_commands(vals['resource_ids'])
                role = self.env['resource.resource'].browse(resource_ids[:1]).planning_default_role_id
                if role:
                    vals['role_id'] = role.id
        slots = super().create(vals_list)
        slots._planning_sync_followers()
        if not self.env.context.get('om_planning_no_recurrence'):
            for slot, repeat in zip(slots, repeat_values):
                if repeat.get('repeat'):
                    slot._planning_create_recurrence(repeat)
        return slots

    @api.model
    def _ids_from_commands(self, commands):
        ids = []
        for command in commands or []:
            if isinstance(command, int):
                if command:
                    ids.append(command)
            elif command[0] == Command.LINK:
                ids.append(command[1])
            elif command[0] == Command.SET:
                ids.extend(command[2])
        return ids

    def _planning_create_recurrence(self, repeat):
        self.ensure_one()
        recurrence = self.env['om.planning.recurrence'].sudo().create({
            'repeat_interval': repeat.get('repeat_interval') or 1,
            'repeat_unit': repeat.get('repeat_unit') or 'week',
            'repeat_type': repeat.get('repeat_type') or 'count',
            'repeat_until': repeat.get('repeat_until'),
            'repeat_count': repeat.get('repeat_count') or 4,
            'company_id': self.company_id.id,
        })
        self.recurrence_id = recurrence
        recurrence._generate_slots(self)

    def write(self, vals):
        vals = dict(vals)
        scope = vals.pop('recurrence_update', None) or self.env.context.get('recurrence_update') or 'this'
        repeat = {key: vals.pop(key) for key in REPEAT_FIELDS if key in vals}
        if 'state' not in vals and PUBLISHED_FIELDS & set(vals) and not self.env.context.get('om_planning_keep_published'):
            published = self.filtered(lambda s: s.state == 'published')
            if published:
                super(OmPlanningSlot, published).write({'changed_since_published': True})
        if vals.get('state') == 'published':
            vals.setdefault('changed_since_published', False)
            vals.setdefault('publication_date', fields.Datetime.now())
        old_resources = {slot.id: slot.resource_ids for slot in self} \
            if 'resource_ids' in vals and not self.env.context.get('om_planning_no_follower_sync') else {}
        if scope != 'this' and len(self) == 1 and self.recurrence_id:
            self._planning_write_series(vals, scope)
        res = super().write(vals) if vals else True
        if old_resources:
            for slot in self:
                slot._planning_sync_followers(old_resources.get(slot.id))
        if repeat:
            self._planning_update_recurrence(repeat)
        return res

    def _planning_write_series(self, vals, scope):
        """ Apply the change of this slot to the next slots (or all) of its series. """
        others = self.recurrence_id.slot_ids - self
        if scope == 'subsequent':
            others = others.filtered(lambda s: s.start_datetime > self.start_datetime)
        if not others:
            return
        others_vals = {key: value for key, value in vals.items() if key in RECURRENCE_FIELDS or key == 'state'}
        start_delta = end_delta = timedelta()
        if 'start_datetime' in vals:
            start_delta = fields.Datetime.to_datetime(vals['start_datetime']) - self.start_datetime
        if 'end_datetime' in vals:
            end_delta = fields.Datetime.to_datetime(vals['end_datetime']) - self.end_datetime
        if start_delta or end_delta:
            for other in others:
                other.with_context(recurrence_update='this').write({
                    **others_vals,
                    'start_datetime': other.start_datetime + start_delta,
                    'end_datetime': other.end_datetime + end_delta,
                })
        elif others_vals:
            others.with_context(recurrence_update='this').write(others_vals)

    def _planning_update_recurrence(self, repeat):
        for slot in self:
            if 'repeat' in repeat and not repeat['repeat']:
                slot.action_stop_recurrence()
            elif repeat.get('repeat') and not slot.recurrence_id:
                values = {key: getattr(slot, key) for key in REPEAT_FIELDS} | repeat
                slot._planning_create_recurrence(values)
            elif slot.recurrence_id:
                values = {key: repeat[key] for key in REPEAT_FIELDS if key in repeat and key != 'repeat'}
                if values:
                    slot.recurrence_id.sudo().write(values)

    def _planning_sync_followers(self, old_resources=None):
        """ Equipment assigned to a person follows the person on their slots. """
        for slot in self:
            people = slot.resource_ids.filtered(lambda r: r.resource_type == 'user')
            wanted = people.following_resource_ids.filtered('active')
            to_remove = self.env['resource.resource']
            if old_resources:
                removed_people = old_resources - slot.resource_ids
                to_remove = removed_people.following_resource_ids - wanted
            commands = [Command.link(r.id) for r in wanted - slot.resource_ids]
            commands += [Command.unlink(r.id) for r in to_remove & slot.resource_ids]
            if commands:
                slot.with_context(om_planning_no_follower_sync=True, om_planning_keep_published=True,
                                  recurrence_update='this').write({'resource_ids': commands})

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        default = default or {}
        for slot, vals in zip(self, vals_list):
            if 'state' not in default:
                vals['state'] = 'draft'
            if 'name' not in default:
                # copies of a slot (series, copy of a period) keep its title
                vals['name'] = slot.name
        return vals_list

    @api.ondelete(at_uninstall=False)
    def _unlink_except_pending_requests(self):
        self.request_ids.filtered(lambda r: r.state == 'pending').sudo().write({'state': 'cancelled'})

    # ------------------------------------------------------------------
    # Engine: conflicts
    # ------------------------------------------------------------------

    def _planning_check(self):
        """ Conflicts of the slots.

        Checks for each resource of each slot: overlap with other slots (a pool can take
        ``planning_capacity`` slots at once, roles with ``allow_overlap`` are ignored), leave or
        public holiday, time outside the working schedule, and the company rules (minimum rest
        between slots, maximum hours per day and per week).

        :return: ``{slot_id: [{'type': str, 'resource_id': int, 'message': str}, ...]}`` with
            type in overlap, leave, outside, rest, max_day, max_week
        """
        result = {slot.id: [] for slot in self}
        slots = self.filtered(lambda s: s.start_datetime and s.end_datetime and s.resource_ids
                              and s.end_datetime > s.start_datetime)
        if not slots:
            return result
        Resource = self.env['resource.resource']
        to_utc = Resource._planning_utc
        resources = slots.resource_ids._origin.sudo()
        start = to_utc(min(slots.mapped('start_datetime'))) - timedelta(days=8)
        stop = to_utc(max(slots.mapped('end_datetime'))) + timedelta(days=8)
        work = resources._planning_work_intervals(start, stop, compute_leaves=False)
        leaves = resources._planning_leave_intervals(start, stop)
        booked = resources._planning_booked_slots(start, stop)
        per_resource = defaultdict(list)
        for other in booked:
            for resource in other.resource_ids & resources:
                per_resource[resource.id].append(other)
        empty = self.env['om.planning.slot']
        for slot in slots:
            company = slot.company_id or self.env.company
            slot_id = slot._origin.id or slot.id
            s, e = to_utc(slot.start_datetime), to_utc(slot.end_datetime)
            period = Intervals([(s, e, empty)])
            problems = result[slot.id]
            for resource in slot.resource_ids._origin.sudo():
                others = [o for o in per_resource[resource.id] if o.id != slot_id]
                # overlap
                if not slot.role_id.allow_overlap:
                    overlapping = [
                        o for o in others
                        if not o.role_id.allow_overlap
                        and to_utc(o.start_datetime) < e and to_utc(o.end_datetime) > s
                    ]
                    if len(overlapping) >= max(resource.planning_capacity, 1):
                        problems.append({
                            'type': 'overlap', 'resource_id': resource.id,
                            'message': self.env._(
                                "%(resource)s is already planned: %(slots)s",
                                resource=resource.name,
                                slots=', '.join(o._planning_short_label(resource) for o in overlapping[:3])),
                        })
                # leaves
                on_leave = leaves.get(resource.id, Intervals()) & period
                if on_leave:
                    leave_records = self.env['resource.calendar.leaves']
                    for _s, _e, recs in on_leave:
                        leave_records |= recs
                    problems.append({
                        'type': 'leave', 'resource_id': resource.id,
                        'message': slot._planning_leave_message(resource, leave_records),
                    })
                # outside working time
                if company.planning_check_working_time and not resource._is_fully_flexible():
                    outside = period - work.get(resource.id, Intervals()) - leaves.get(resource.id, Intervals())
                    # the break of the slot may fall in a pause of the schedule (lunch)
                    if sum_intervals(outside) > slot.break_hours + 1 / 60:
                        problems.append({
                            'type': 'outside', 'resource_id': resource.id,
                            'message': self.env._(
                                "%(resource)s: %(hours)s h outside the working schedule",
                                resource=resource.name, hours=round(sum_intervals(outside), 2)),
                        })
                if resource.resource_type != 'user':
                    continue
                # minimum rest
                if company.planning_min_rest_hours:
                    rest = timedelta(hours=company.planning_min_rest_hours)
                    tz = ZoneInfo(resource.tz or 'UTC')
                    slot_day = s.astimezone(tz).date()
                    for other in others:
                        o_s, o_e = to_utc(other.start_datetime), to_utc(other.end_datetime)
                        # the rest is checked between the work of two days (split shifts are allowed)
                        if o_s.astimezone(tz).date() == slot_day:
                            continue
                        gap = s - o_e if o_e <= s else o_s - e if o_s >= e else None
                        if gap is not None and gap < rest:
                            problems.append({
                                'type': 'rest', 'resource_id': resource.id,
                                'message': self.env._(
                                    "%(resource)s: only %(hours)s h of rest before or after %(slot)s "
                                    "(minimum %(minimum)s h)",
                                    resource=resource.name, hours=round(gap.total_seconds() / 3600, 2),
                                    slot=other._planning_short_label(resource),
                                    minimum=company.planning_min_rest_hours),
                            })
                            break
                # maximum hours
                if company.planning_max_hours_day or company.planning_max_hours_week:
                    tz = ZoneInfo(resource.tz or 'UTC')
                    local_day = s.astimezone(tz).date()
                    week = local_day.isocalendar()[:2]
                    day_hours = slot.allocated_hours
                    week_hours = slot.allocated_hours
                    for other in others:
                        other_day = to_utc(other.start_datetime).astimezone(tz).date()
                        if other_day == local_day:
                            day_hours += other.allocated_hours
                        if other_day.isocalendar()[:2] == week:
                            week_hours += other.allocated_hours
                    if company.planning_max_hours_day and day_hours > company.planning_max_hours_day + 0.001:
                        problems.append({
                            'type': 'max_day', 'resource_id': resource.id,
                            'message': self.env._(
                                "%(resource)s: %(hours)s h planned on %(day)s (maximum %(maximum)s h)",
                                resource=resource.name, hours=round(day_hours, 2), day=local_day,
                                maximum=company.planning_max_hours_day),
                        })
                    if company.planning_max_hours_week and week_hours > company.planning_max_hours_week + 0.001:
                        problems.append({
                            'type': 'max_week', 'resource_id': resource.id,
                            'message': self.env._(
                                "%(resource)s: %(hours)s h planned in week %(week)s (maximum %(maximum)s h)",
                                resource=resource.name, hours=round(week_hours, 2), week=week[1],
                                maximum=company.planning_max_hours_week),
                        })
        return result

    def _planning_leave_message(self, resource, leaves):
        """ Text of a conflict with leaves (``resource.calendar.leaves``). """
        names = ', '.join(name for name in leaves.mapped('name') if name) or self.env._("leave")
        return self.env._("%(resource)s is not available: %(leaves)s", resource=resource.name, leaves=names)

    def _planning_short_label(self, resource=None):
        self.ensure_one()
        tz = ZoneInfo((resource and resource.tz) or self.env.user.tz or 'UTC')
        start = self.start_datetime.replace(tzinfo=UTC).astimezone(tz)
        end = self.end_datetime.replace(tzinfo=UTC).astimezone(tz)
        label = self.role_id.name or self.name or self.env._("slot")
        if end.date() != start.date():
            return f"{label} {start:%m/%d %H:%M}-{end:%m/%d %H:%M}"
        return f"{label} {start:%m/%d %H:%M}-{end:%H:%M}"

    @api.constrains('resource_ids', 'company_id')
    def _check_resource_company(self):
        for slot in self:
            wrong = slot.resource_ids.filtered(lambda r: r.company_id and r.company_id != slot.company_id)
            if wrong:
                raise ValidationError(self.env._(
                    "The resources %s belong to another company.", ', '.join(wrong.mapped('name'))))

    # ------------------------------------------------------------------
    # Gantt hooks
    # ------------------------------------------------------------------

    @api.model
    def gantt_unavailability(self, start_date, end_date, scale, group_bys=None, rows=None):
        rows = super().gantt_unavailability(start_date, end_date, scale, group_bys=group_bys, rows=rows)
        resource_ids = set()

        def collect(row_list):
            for row in row_list or []:
                if row.get('groupedBy') and row['groupedBy'][-1] == 'resource_ids' and row.get('resId'):
                    resource_ids.add(row['resId'])
                collect(row.get('rows'))

        collect(rows)
        if not resource_ids:
            return rows
        resources = self.env['resource.resource'].sudo().browse(sorted(resource_ids)).exists()
        work = resources._planning_work_intervals(start_date, end_date)
        to_utc = resources._planning_utc
        full = Intervals([(to_utc(start_date), to_utc(end_date), self.env['om.planning.slot'])])
        unavailable = {
            resource.id: [
                {'start': s.astimezone(UTC).replace(tzinfo=None), 'stop': e.astimezone(UTC).replace(tzinfo=None)}
                for s, e, _recs in full - work.get(resource.id, Intervals())
            ]
            for resource in resources
        }

        def fill(row_list):
            for row in row_list or []:
                if row.get('groupedBy') and row['groupedBy'][-1] == 'resource_ids' and row.get('resId'):
                    row['unavailabilities'] = unavailable.get(row['resId'], [])
                fill(row.get('rows'))

        fill(rows)
        return rows

    @api.model
    def _gantt_progress_bar(self, field, res_ids, start, stop):
        if field == 'resource_ids':
            resources = self.env['resource.resource'].sudo().browse(res_ids).exists()
            capacity = resources._planning_capacity_hours(start, stop)
            booked = resources._planning_booked_hours(start, stop)
            return {
                resource.id: {
                    'value': round(booked.get(resource.id, 0.0), 2),
                    'max': capacity.get(resource.id, 0.0),
                    'label': self.env._("%(planned)s / %(capacity)s h",
                                        planned=round(booked.get(resource.id, 0.0), 1),
                                        capacity=round(capacity.get(resource.id, 0.0), 1)),
                }
                for resource in resources
            }
        if field == 'role_id':
            roles = self.env['om.planning.role'].sudo().browse(res_ids).exists()
            result = {}
            for role in roles:
                resources = role.resource_ids.filtered('active')
                capacity = sum(resources._planning_capacity_hours(start, stop).values())
                slots = self.sudo().search([
                    ('role_id', '=', role.id),
                    ('start_datetime', '<', stop), ('end_datetime', '>', start),
                ])
                planned = sum(slot._planning_hours_between(start, stop) * max(len(slot.resource_ids), 1)
                              for slot in slots)
                result[role.id] = {
                    'value': round(planned, 2), 'max': round(capacity, 2),
                    'label': self.env._("%(planned)s / %(capacity)s h",
                                        planned=round(planned, 1), capacity=round(capacity, 1)),
                }
            return result
        return super()._gantt_progress_bar(field, res_ids, start, stop)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_publish(self):
        self.filtered(lambda s: s.state == 'draft' or s.changed_since_published).write({'state': 'published'})
        return True

    def action_unpublish(self):
        self.write({'state': 'draft', 'changed_since_published': False})
        return True

    def action_stop_recurrence(self):
        for slot in self.filtered('recurrence_id'):
            recurrence = slot.recurrence_id
            later = recurrence.slot_ids.filtered(lambda s: s.start_datetime > slot.start_datetime)
            later.unlink()
            remaining = recurrence.slot_ids
            remaining.write({'recurrence_id': False})
            recurrence.sudo().unlink()
        return True

    def action_unlink_subsequent(self):
        self.ensure_one()
        if not self.recurrence_id:
            self.unlink()
        else:
            self.recurrence_id.slot_ids.filtered(lambda s: s.start_datetime >= self.start_datetime).unlink()
        return {'type': 'ir.actions.act_window_close'}

    def action_unlink_all(self):
        self.ensure_one()
        (self.recurrence_id.slot_ids or self).unlink()
        return {'type': 'ir.actions.act_window_close'}

    @api.model
    def action_copy_previous(self, start, stop, scale='week', domain=None):
        """ Copy the slots of the previous period (shifted by one period) as drafts.

        :param str start: start of the visible period (UTC)
        :param str stop: end of the visible period (UTC)
        :param str scale: day, week, month or year
        :param list domain: domain of the view (filters)
        :return: number of slots created
        """
        start, stop = fields.Datetime.to_datetime(start), fields.Datetime.to_datetime(stop)
        delta = relativedelta(months=1) if scale == 'month' else relativedelta(years=1) if scale == 'year' \
            else timedelta(seconds=round((stop - start).total_seconds() / 86400) * 86400)
        if not delta:
            return 0
        previous = self.search(Domain.AND([
            Domain(domain or []),
            Domain([('start_datetime', '>=', start - delta), ('start_datetime', '<', stop - delta)]),
        ]))
        existing = self.search([('start_datetime', '>=', start), ('start_datetime', '<', stop)])
        keys = {(s.start_datetime, s.end_datetime, s.role_id.id, tuple(sorted(s.resource_ids.ids))) for s in existing}
        values_list = []
        for slot in previous:
            new_start, new_end = slot.start_datetime + delta, slot.end_datetime + delta
            key = (new_start, new_end, slot.role_id.id, tuple(sorted(slot.resource_ids.ids)))
            if key in keys:
                continue
            values_list.append(slot.copy_data({
                'start_datetime': new_start,
                'end_datetime': new_end,
                'recurrence_id': False,
                'state': 'draft',
            })[0])
        self.with_context(om_planning_no_recurrence=True).create(values_list)
        return len(values_list)

    @api.model
    def action_publish_period(self, start, stop, domain=None):
        """ Open the "Publish & Send" form for the visible period of the Gantt. """
        action = self.env['ir.actions.act_window']._for_xml_id('om_planning.action_om_planning_schedule_send')
        action['context'] = {
            'default_start_datetime': start,
            'default_end_datetime': stop,
        }
        return action

    def _planning_request(self, request_type, **values):
        self.ensure_one()
        resource = values.pop('resource', None) or self.env['resource.resource'].search(
            [('user_id', '=', self.env.uid)], limit=1)
        if not resource:
            raise UserError(self.env._("Your user is not linked to a planning resource."))
        return self.env['om.planning.request'].create({
            'slot_id': self.id,
            'request_type': request_type,
            'resource_id': resource.id,
            **values,
        })

    def action_request_claim(self):
        for slot in self:
            if not slot.is_open:
                raise UserError(self.env._("Only open slots can be claimed."))
            slot._planning_request('claim')
        return True

    def action_request_unassign(self):
        for slot in self:
            slot._planning_request('unassign')
        return True

    def action_request_switch(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Ask to Switch"),
            'res_model': 'om.planning.request',
            'view_mode': 'form',
            'views': [(self.env.ref('om_planning.om_planning_request_view_form_switch').id, 'form')],
            'target': 'new',
            'context': {'default_slot_id': self.id, 'default_request_type': 'switch'},
        }

    def action_open_source(self):
        self.ensure_one()
        record = self.source_ref
        if not record:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': record._name,
            'res_id': record.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    # ------------------------------------------------------------------
    # Calendar feed
    # ------------------------------------------------------------------

    def _planning_ics(self, name):
        """ iCalendar text of the slots. """
        def stamp(dt):
            return dt.strftime('%Y%m%dT%H%M%SZ')

        def escape(text):
            return (text or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

        base_url = self.browse().get_base_url()
        host = base_url.split('//')[-1].split('/')[0]
        lines = [
            'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Odoo Mates//Planning//EN',
            'CALSCALE:GREGORIAN', f'X-WR-CALNAME:{escape(name)}',
        ]
        now = stamp(fields.Datetime.now())
        for slot in self:
            description = slot.note or ''
            if slot.resource_ids:
                description = ', '.join(slot.resource_ids.mapped('name')) + ('\n' + description if description else '')
            lines += [
                'BEGIN:VEVENT',
                f'UID:om-planning-slot-{slot.id}@{host}',
                f'DTSTAMP:{now}',
                f'DTSTART:{stamp(slot.start_datetime)}',
                f'DTEND:{stamp(slot.end_datetime)}',
                f'SUMMARY:{escape(slot.role_id.name or slot.name or self.env._("Shift"))}',
                f'DESCRIPTION:{escape(description)}',
                'END:VEVENT',
            ]
        lines.append('END:VCALENDAR')
        return '\r\n'.join(lines) + '\r\n'

    @api.model
    def _planning_demo_localize(self, slot_ids):
        """ Demo data: the dates of the slots are written in the timezone of their resource. """
        default_tz = self.env.ref('base.user_admin', raise_if_not_found=False).tz or 'UTC'
        for slot in self.browse(slot_ids).exists():
            tz = ZoneInfo(slot.resource_ids[:1].tz or default_tz)
            slot.with_context(om_planning_keep_published=True, recurrence_update='all').write({
                'start_datetime': slot.start_datetime.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None),
                'end_datetime': slot.end_datetime.replace(tzinfo=tz).astimezone(UTC).replace(tzinfo=None),
            })
