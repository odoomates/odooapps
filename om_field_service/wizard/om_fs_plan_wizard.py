from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


def _distance_km(lat1, lng1, lat2, lng2):
    """ Great-circle distance between two points, in km. """
    lat1, lng1, lat2, lng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


class OmFsPlanWizard(models.TransientModel):
    _name = 'om.fs.plan.wizard'
    _description = "Plan a Field Service Job"

    task_id = fields.Many2one('project.task', string="Job", required=True, ondelete='cascade')
    partner_id = fields.Many2one(related='task_id.partner_id', string="Customer")
    site_address = fields.Char(related='task_id.site_address', string="Site Address")
    start = fields.Datetime(string="Start", required=True)
    duration = fields.Float(string="Duration", required=True, default=1.0)
    end = fields.Datetime(compute='_compute_end', string="End")
    search_days = fields.Integer(string="Search Days", default=7,
                                 help="Days after the start in which free technicians are searched.")
    technician_ids = fields.Many2many('hr.employee', string="Technicians")
    suggestion_ids = fields.One2many('om.fs.plan.suggestion', 'wizard_id', string="Suggestions")
    conflict_info = fields.Text(compute='_compute_conflict_info', string="Conflicts")

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        task = self.env['project.task'].browse(res.get('task_id') or self.env.context.get('default_task_id'))
        if task:
            if 'default_duration' not in self.env.context:
                res['duration'] = task._fs_duration()
            res.setdefault('technician_ids', [Command.set(task.technician_ids.ids)])
            if task.planned_start:
                res.setdefault('start', task.planned_start)
        if not res.get('start'):
            now = datetime.now()
            res['start'] = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        wizards = super().create(vals_list)
        wizards._fs_suggest()
        return wizards

    @api.depends('start', 'duration')
    def _compute_end(self):
        for wizard in self:
            wizard.end = wizard.start and wizard.start + timedelta(hours=wizard.duration or 0)

    @api.depends('start', 'duration', 'technician_ids')
    def _compute_conflict_info(self):
        for wizard in self:
            wizard.conflict_info = False
            if not (wizard.start and wizard.duration > 0 and wizard.technician_ids):
                continue
            task = wizard.task_id
            values = {
                **task._planning_slot_values(),
                'start_datetime': wizard.start,
                'end_datetime': wizard.end,
                'resource_ids': [Command.set(wizard.technician_ids.resource_id.ids)],
            }
            values.pop('source_ref', None)
            existing = task._fs_slots()
            Slot = self.env['om.planning.slot'].sudo()
            slot = Slot.new(values, origin=existing) if len(existing) == 1 else Slot.new(values)
            problems = slot._planning_check().get(slot.id, [])
            wizard.conflict_info = '\n'.join(p['message'] for p in problems) or False

    # ------------------------------------------------------------------
    # Suggestions
    # ------------------------------------------------------------------

    def _fs_candidate_resources(self):
        self.ensure_one()
        role = self.task_id._planning_role()
        resources = role.resource_ids if role else self.env['resource.resource']
        if not resources:
            resources = self.env['om.planning.slot']._fs_technician_resources()
        return resources.filtered(lambda r: r.active and r.employee_id and r.resource_type == 'user'
                                  and (not r.company_id or r.company_id == self.task_id._fs_company()))

    def _fs_previous_point(self, resource, moment):
        """ Where the technician is before ``moment``: the site of their previous job of the day,
        or else their work address. """
        day_start = moment.replace(hour=0, minute=0, second=0)
        slot = self.env['om.planning.slot'].sudo().search([
            ('resource_ids', 'in', resource.ids),
            ('fs_job_id', '!=', False),
            ('fs_job_id', '!=', self.task_id.id),
            ('end_datetime', '<=', moment),
            ('end_datetime', '>=', day_start),
        ], order='end_datetime desc', limit=1)
        partner = slot.fs_job_id.site_partner_id
        if not (partner.partner_latitude or partner.partner_longitude):
            partner = resource.employee_id[:1].address_id
        if partner.partner_latitude or partner.partner_longitude:
            return partner.partner_latitude, partner.partner_longitude
        return None

    def _fs_suggest(self):
        Suggestion = self.env['om.fs.plan.suggestion']
        for wizard in self:
            wizard.suggestion_ids.unlink()
            if not (wizard.start and wizard.duration > 0):
                continue
            resources = wizard._fs_candidate_resources()
            if not resources:
                continue
            start = wizard.start
            duration = timedelta(hours=wizard.duration)
            horizon = start + timedelta(days=max(wizard.search_days, 1))
            exclude = wizard.task_id._fs_slots()
            free = resources._planning_free_intervals(start, horizon, exclude_slots=exclude)
            site = wizard.task_id.site_partner_id
            has_site = bool(site.partner_latitude or site.partner_longitude)
            day_start = start.replace(hour=0, minute=0, second=0)
            load = resources._planning_booked_hours(day_start, day_start + timedelta(days=1))
            values_list = []
            for resource in resources:
                first = None
                for s, e, _recs in free[resource.id]:
                    s0 = max(s.replace(tzinfo=None), start)
                    if e.replace(tzinfo=None) - s0 >= duration:
                        first = s0
                        break
                if not first:
                    continue
                distance = 0.0
                point = has_site and wizard._fs_previous_point(resource, first)
                if point:
                    distance = round(_distance_km(point[0], point[1], site.partner_latitude,
                                                  site.partner_longitude), 1)
                values_list.append({
                    'wizard_id': wizard.id,
                    'employee_id': resource.employee_id[:1].id,
                    'start': first,
                    'free_at_start': first <= start + timedelta(minutes=1),
                    'distance_km': distance,
                    'has_distance': bool(point),
                    'load_hours': round(load.get(resource.id, 0.0), 2),
                })
            values_list.sort(key=lambda v: (
                not v['free_at_start'], v['start'], not v['has_distance'], v['distance_km'], v['load_hours']))
            for sequence, values in enumerate(values_list[:10]):
                values['sequence'] = sequence
            Suggestion.create(values_list[:10])

    def _fs_reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Plan %s", self.task_id.display_name),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def action_refresh(self):
        self._fs_suggest()
        return self._fs_reopen()

    def action_confirm(self):
        self.ensure_one()
        if not self.technician_ids:
            raise UserError(self.env._("Choose at least one technician."))
        if self.duration <= 0:
            raise UserError(self.env._("The duration must be positive."))
        task = self.task_id
        values = {
            'planned_start': self.start,
            'planned_end': self.end,
            'technician_ids': [Command.set(self.technician_ids.ids)],
            'allocated_hours': task.allocated_hours or self.duration,
        }
        if task.job_state == 'new':
            values['job_state'] = 'planned'
        task.write(values)
        return {'type': 'ir.actions.act_window_close'}


class OmFsPlanSuggestion(models.TransientModel):
    _name = 'om.fs.plan.suggestion'
    _description = "Free Technician Suggestion"
    _order = 'sequence, id'

    wizard_id = fields.Many2one('om.fs.plan.wizard', string="Wizard", required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    employee_id = fields.Many2one('hr.employee', string="Technician", required=True)
    start = fields.Datetime(string="Free From")
    free_at_start = fields.Boolean(string="Free at the Time Asked")
    distance_km = fields.Float(string="Distance (km)", digits=(16, 1),
                               help="From the previous job of the day of the technician, or their work address.")
    has_distance = fields.Boolean(string="Distance Known")
    load_hours = fields.Float(string="Planned That Day")

    def action_choose(self):
        self.ensure_one()
        wizard = self.wizard_id
        wizard.write({
            'technician_ids': [Command.set(self.employee_id.ids)],
            'start': self.start,
        })
        return wizard._fs_reopen()

    def action_add(self):
        self.ensure_one()
        self.wizard_id.technician_ids = [Command.link(self.employee_id.id)]
        return self.wizard_id._fs_reopen()
