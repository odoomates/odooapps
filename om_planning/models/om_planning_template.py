from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def float_to_time(hours):
    hours = max(0.0, min(hours, 24.0))
    if hours >= 24.0:
        return time.max
    minutes = round(hours * 60)
    return time(minutes // 60, minutes % 60)


class OmPlanningTemplate(models.Model):
    _name = 'om.planning.template'
    _description = "Planning Shift Template"
    _order = 'sequence, start_time, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(string="Code", size=8, help="Short code shown on rosters, e.g. M, E or N.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    start_time = fields.Float(string="Start Hour", required=True, default=8.0)
    end_time = fields.Float(string="End Hour", required=True, default=17.0,
                            help="An end hour before the start hour ends the next day.")
    break_hours = fields.Float(string="Break", default=1.0)
    duration = fields.Float(compute='_compute_duration', string="Hours")
    role_id = fields.Many2one('om.planning.role', string="Role")
    color = fields.Integer(string="Color")
    company_id = fields.Many2one('res.company', string="Company")

    @api.depends('start_time', 'end_time', 'break_hours')
    def _compute_duration(self):
        for template in self:
            span = template.end_time - template.start_time
            if span <= 0:
                span += 24
            template.duration = max(span - template.break_hours, 0.0)

    @api.constrains('start_time', 'end_time', 'break_hours')
    def _check_hours(self):
        for template in self:
            if not (0 <= template.start_time < 24 and 0 <= template.end_time <= 24):
                raise ValidationError(self.env._("The hours of a template must be between 0 and 24."))
            if template.break_hours < 0:
                raise ValidationError(self.env._("The break cannot be negative."))

    @api.depends('name', 'code', 'start_time', 'end_time')
    def _compute_display_name(self):
        for template in self:
            hours = '%02d:%02d - %02d:%02d' % (
                int(template.start_time), round(template.start_time % 1 * 60),
                int(template.end_time), round(template.end_time % 1 * 60))
            prefix = f'[{template.code}] ' if template.code else ''
            template.display_name = f'{prefix}{template.name or ""} ({hours})'

    def _get_period(self, day, tz):
        """ Start and end of the template on ``day`` in the timezone ``tz``.

        :param date day: the day the slot starts
        :param str tz: timezone name
        :return: (start, stop) naive UTC datetimes
        """
        self.ensure_one()
        zone = ZoneInfo(tz or 'UTC')
        start = datetime.combine(day, float_to_time(self.start_time), tzinfo=zone)
        end_day = day if self.end_time > self.start_time else day + timedelta(days=1)
        end = datetime.combine(end_day, float_to_time(self.end_time), tzinfo=zone)
        if self.end_time >= 24:
            end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
        utc = ZoneInfo('UTC')
        return start.astimezone(utc).replace(tzinfo=None), end.astimezone(utc).replace(tzinfo=None)
