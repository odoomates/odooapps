from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.date_utils import sum_intervals
from odoo.tools.intervals import Intervals


class OmPlanningRotationApply(models.TransientModel):
    _name = 'om.planning.rotation.apply'
    _description = "Apply a Planning Rotation"

    rotation_id = fields.Many2one('om.planning.rotation', string="Rotation", required=True)
    resource_ids = fields.Many2many('resource.resource', string="Resources", required=True)
    date_from = fields.Date(string="From", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="To", required=True,
                          default=lambda self: fields.Date.context_today(self) + timedelta(days=27))
    start_day = fields.Integer(string="Start at Day", default=1,
                               help="Day of the cycle used on the first date.")
    stagger = fields.Boolean(string="Stagger Resources",
                             help="Each next resource starts one day later in the cycle.")
    skip_leaves = fields.Boolean(string="Skip Days Off and Leaves", default=True,
                                 help="No slot on days the resource is on leave.")
    replace_drafts = fields.Boolean(string="Replace Draft Slots", default=True,
                                    help="Delete the draft slots of the resources in the period first.")
    publish = fields.Boolean(string="Publish Directly")

    @api.onchange('rotation_id')
    def _onchange_rotation_id(self):
        if self.rotation_id.role_id and not self.resource_ids:
            self.resource_ids = self.rotation_id.role_id.resource_ids

    def action_apply(self):
        self.ensure_one()
        lines = self.rotation_id.line_ids.sorted(lambda l: (l.sequence, l.id))
        if not lines:
            raise UserError(self.env._("The rotation has no day."))
        if self.date_to < self.date_from:
            raise UserError(self.env._("The end date must be after the start date."))
        Slot = self.env['om.planning.slot']
        days = (self.date_to - self.date_from).days + 1
        if self.replace_drafts:
            Slot.search([
                ('resource_ids', 'in', self.resource_ids.ids),
                ('state', '=', 'draft'),
                ('start_datetime', '>=', fields.Datetime.to_datetime(self.date_from) - timedelta(hours=14)),
                ('start_datetime', '<', fields.Datetime.to_datetime(self.date_to) + timedelta(days=1, hours=14)),
            ]).filtered(lambda s: s.template_id in lines.template_id).unlink()
        values_list = []
        for index, resource in enumerate(self.resource_ids):
            offset = (self.start_day - 1) + (index if self.stagger else 0)
            leaves = None
            if self.skip_leaves:
                leaves = resource._planning_leave_intervals(
                    fields.Datetime.to_datetime(self.date_from) - timedelta(days=1),
                    fields.Datetime.to_datetime(self.date_to) + timedelta(days=2))[resource.id]
            for day_index in range(days):
                line = lines[(day_index + offset) % len(lines)]
                template = line.template_id
                if not template:
                    continue
                day = self.date_from + timedelta(days=day_index)
                start, stop = template._get_period(day, resource.tz)
                if leaves:
                    to_utc = resource._planning_utc
                    overlap = leaves & Intervals([(to_utc(start), to_utc(stop), self.env['om.planning.slot'])])
                    if sum_intervals(overlap) >= (stop - start).total_seconds() / 3600 / 2:
                        continue
                values_list.append({
                    'resource_ids': [(6, 0, resource.ids)],
                    'role_id': (template.role_id or self.rotation_id.role_id or resource.planning_default_role_id).id,
                    'template_id': template.id,
                    'start_datetime': start,
                    'end_datetime': stop,
                    'break_hours': template.break_hours,
                    'state': 'published' if self.publish else 'draft',
                    'company_id': (resource.company_id or self.env.company).id,
                })
        slots = Slot.create(values_list)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._("%s slots created.", len(slots)),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
