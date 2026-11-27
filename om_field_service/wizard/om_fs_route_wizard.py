from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain

from .om_fs_plan_wizard import _distance_km

# a job keeps its time when it is started, closed or done by a crew
MOVABLE_STATES = ('new', 'planned')
ROUND_MINUTES = 5


def _route_length(start, points, order, back=False):
    """ Length (km) of the route from ``start`` through ``points`` in ``order``. """
    length = 0.0
    previous = start
    for index in order:
        length += _distance_km(*previous, *points[index])
        previous = points[index]
    if back and order:
        length += _distance_km(*previous, *start)
    return length


def _nearest_neighbour(start, points):
    """ Order of the points: always go to the nearest point not visited yet. """
    left = set(range(len(points)))
    order = []
    current = start
    while left:
        index = min(left, key=lambda i: (_distance_km(*current, *points[i]), i))
        order.append(index)
        left.remove(index)
        current = points[index]
    return order


def _two_opt(start, points, order, back=False):
    """ Improve the order by reversing parts of the route while it gets shorter (2-opt). """
    best = list(order)
    best_length = _route_length(start, points, best, back)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                length = _route_length(start, points, candidate, back)
                if length < best_length - 1e-9:
                    best, best_length = candidate, length
                    improved = True
    return best


def optimise_route(start, points, back=False):
    """ Short route from ``start`` through every point, without any external service:
    nearest neighbour, then 2-opt on the great-circle distance.

    :param tuple start: (latitude, longitude) where the route starts
    :param list points: (latitude, longitude) of the stops
    :param bool back: the route ends at the start
    :return: the indexes of the points in their visit order
    """
    if len(points) < 2:
        return list(range(len(points)))
    return _two_opt(start, points, _nearest_neighbour(start, points), back)


def maps_route_url(points):
    """ Google Maps link of a route through the points (latitude, longitude), in this order. """
    if len(points) < 2:
        return False
    return 'https://www.google.com/maps/dir/' + '/'.join(f'{lat},{lng}' for lat, lng in points)


def _round_up(value):
    minute = (value.minute // ROUND_MINUTES + bool(value.minute % ROUND_MINUTES)) * ROUND_MINUTES
    return value.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minute)


class OmFsRouteWizard(models.TransientModel):
    _name = 'om.fs.route.wizard'
    _description = "Optimise the Route of a Technician"

    employee_id = fields.Many2one('hr.employee', string="Technician", required=True,
                                  domain="[('is_technician', '=', True)]")
    date = fields.Date(string="Day", required=True, default=fields.Date.context_today)
    start_partner_id = fields.Many2one('res.partner', compute='_compute_start_partner_id', string="Start From",
                                       help="Work address of the technician, or the address of the company.")
    line_ids = fields.One2many('om.fs.route.wizard.line', 'wizard_id', string="Stops")
    distance_before = fields.Float(string="Distance Now (km)", digits=(16, 1), readonly=True)
    distance_after = fields.Float(string="Optimised Distance (km)", digits=(16, 1), readonly=True)
    maps_url = fields.Char(string="Route in Maps", readonly=True)
    note = fields.Text(string="Note", readonly=True)
    can_apply = fields.Boolean(readonly=True)

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if not res.get('employee_id'):
            employee = self.env.user.employee_id
            if employee.sudo().is_technician:
                res['employee_id'] = employee.id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        for wizard in wizards:
            wizard.write(wizard._fs_route_values())
        return wizards

    @api.depends('employee_id')
    def _compute_start_partner_id(self):
        for wizard in self:
            employee = wizard.employee_id
            wizard.start_partner_id = employee._fs_route_start_partner() if employee else False

    @api.onchange('employee_id', 'date')
    def _onchange_route(self):
        if self.employee_id and self.date:
            self.update(self._fs_route_values())

    # ------------------------------------------------------------------
    # Route
    # ------------------------------------------------------------------

    def _fs_day_jobs(self):
        self.ensure_one()
        tz = ZoneInfo(self.employee_id.sudo().resource_id.tz or self.env.user.tz or 'UTC')
        start = datetime.combine(self.date, time.min, tz).astimezone(UTC).replace(tzinfo=None)
        stop = start + timedelta(days=1)
        return self.env['project.task'].search(
            Domain('is_field_service', '=', True) & Domain('technician_ids', 'in', self.employee_id.ids)
            & Domain('planned_start', '<', stop) & Domain('planned_end', '>', start)
            & Domain('job_state', '!=', 'cancelled'),
            order='planned_start, id')

    def _fs_movable(self, job):
        partner = job.site_partner_id or job.partner_id
        return (job.job_state in MOVABLE_STATES and job.sudo().technician_ids.ids == self.employee_id.ids
                and bool(partner.partner_latitude or partner.partner_longitude)
                and len(job._fs_slots()) <= 1)

    @api.model
    def _fs_point(self, partner):
        return (partner.partner_latitude, partner.partner_longitude) \
            if partner and (partner.partner_latitude or partner.partner_longitude) else None

    def _fs_route_plan(self):
        """ The new times of the jobs of the day.

        :return: (list of (job, start, end, km from the previous stop), fixed jobs, start point)
        """
        self.ensure_one()
        jobs = self._fs_day_jobs()
        movable = jobs.filtered(self._fs_movable)
        fixed = jobs - movable
        start_point = self._fs_point(self.employee_id._fs_route_start_partner())
        points = [self._fs_point(job.site_partner_id or job.partner_id) for job in movable]
        if not start_point and points:
            start_point = points[0]
        order = optimise_route(start_point, points) if points else []
        speed = max((self.employee_id.sudo().company_id or self.env.company).fs_route_speed or 40.0, 1.0)
        busy = [(job.planned_start, job.planned_end, self._fs_point(job.site_partner_id or job.partner_id))
                for job in fixed]
        moment = min(movable.mapped('planned_start')) if movable else False
        previous = start_point
        plan = []
        for rank, index in enumerate(order):
            job = movable[index]
            point = points[index]
            km = _distance_km(*previous, *point)
            duration = job.planned_end - job.planned_start
            begin = moment if rank == 0 else _round_up(moment + timedelta(hours=km / speed))
            # after the jobs which keep their time
            moved = True
            while moved:
                moved = False
                for busy_start, busy_end, busy_point in busy:
                    if begin < busy_end and begin + duration > busy_start:
                        travel = _distance_km(*busy_point, *point) / speed if busy_point else 0.0
                        begin = _round_up(busy_end + timedelta(hours=travel))
                        moved = True
            plan.append((job, begin, begin + duration, km))
            moment = begin + duration
            previous = point
        return plan, fixed, start_point

    def _fs_route_values(self):
        self.ensure_one()
        plan, fixed, start_point = self._fs_route_plan()
        tz = ZoneInfo(self.employee_id.sudo().resource_id.tz or self.env.user.tz or 'UTC')
        points_now = [self._fs_point(job.site_partner_id or job.partner_id)
                      for job, _begin, _end, _km in sorted(plan, key=lambda p: (p[0].planned_start, p[0].id))]
        lines = [Command.clear()]
        for sequence, (job, begin, end, km) in enumerate(plan, 1):
            lines.append(Command.create({
                'sequence': sequence,
                'task_id': job.id,
                'distance_km': km,
                'old_start': job.planned_start,
                'new_start': begin,
                'new_end': end,
            }))
        # the route still to drive: the jobs done are left out
        fixed = fixed.filtered(lambda j: j.job_state != 'done')
        stops = sorted([(begin, self._fs_point(job.site_partner_id or job.partner_id)) for job, begin, _e, _k in plan]
                       + [(job.planned_start, self._fs_point(job.site_partner_id or job.partner_id)) for job in fixed],
                       key=lambda s: s[0])
        route_points = [start_point] + [point for _begin, point in stops if point] if start_point else []
        notes = []
        for job in fixed:
            local = job.planned_start.replace(tzinfo=UTC).astimezone(tz)
            notes.append(self.env._("%(time)s %(job)s keeps its time", time=local.strftime('%H:%M'),
                                    job=job.display_name))
        if not plan:
            notes.insert(0, self.env._("No planned job of this technician on this day can be moved: jobs started, "
                                       "done by a crew, over several days or without GPS coordinates keep their time."))
        return {
            'line_ids': lines,
            'distance_before': _route_length(start_point, points_now, range(len(points_now))) if start_point else 0.0,
            'distance_after': sum(km for _job, _b, _e, km in plan),
            'maps_url': maps_route_url(route_points),
            'note': '\n'.join(notes) or False,
            'can_apply': any(job.planned_start != begin for job, begin, _e, _k in plan),
        }

    def action_refresh(self):
        self.ensure_one()
        self.write(self._fs_route_values())
        return self._fs_reopen()

    def action_apply(self):
        self.ensure_one()
        plan, _fixed, _start = self._fs_route_plan()
        if not plan:
            raise UserError(self.env._("There is no job to reorder."))
        for job, begin, end, _km in plan:
            if job.planned_start != begin:
                job.write({'planned_start': begin, 'planned_end': end})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._("The jobs of %(technician)s are in their new order.",
                                      technician=self.employee_id.sudo().name),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _fs_reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'name': self.env._("Optimise the Route"),
        }


class OmFsRouteWizardLine(models.TransientModel):
    _name = 'om.fs.route.wizard.line'
    _description = "Stop of an Optimised Route"
    _order = 'sequence, id'

    wizard_id = fields.Many2one('om.fs.route.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(string="Stop")
    task_id = fields.Many2one('project.task', string="Job", required=True, ondelete='cascade')
    partner_id = fields.Many2one(related='task_id.partner_id', string="Customer")
    site_address = fields.Char(related='task_id.site_address', string="Site Address")
    distance_km = fields.Float(string="Distance (km)", digits=(16, 1))
    old_start = fields.Datetime(string="Planned Now")
    new_start = fields.Datetime(string="New Start")
    new_end = fields.Datetime(string="New End")
    moved = fields.Boolean(compute='_compute_moved', string="Moved")

    @api.depends('old_start', 'new_start')
    def _compute_moved(self):
        for line in self:
            line.moved = line.old_start != line.new_start
