from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

MAX_OCCURRENCES = 366


class OmPlanningRecurrence(models.Model):
    _name = 'om.planning.recurrence'
    _description = "Planning Recurrence"

    slot_ids = fields.One2many('om.planning.slot', 'recurrence_id', string="Slots")
    repeat_interval = fields.Integer(string="Repeat Every", default=1, required=True)
    repeat_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
    ], string="Repeat Unit", default='week', required=True)
    repeat_type = fields.Selection([
        ('until', 'Until'),
        ('count', 'Number of Times'),
    ], string="Repeat Type", default='count', required=True)
    repeat_until = fields.Date(string="Repeat Until")
    repeat_count = fields.Integer(string="Repetitions", default=4)
    company_id = fields.Many2one('res.company', string="Company")

    @api.constrains('repeat_interval', 'repeat_type', 'repeat_until', 'repeat_count')
    def _check_repeat(self):
        for recurrence in self:
            if recurrence.repeat_interval < 1:
                raise ValidationError(self.env._("The repeat interval must be at least 1."))
            if recurrence.repeat_type == 'until' and not recurrence.repeat_until:
                raise ValidationError(self.env._("Set the date until which the slot repeats."))
            if recurrence.repeat_type == 'count' and not 1 <= recurrence.repeat_count <= MAX_OCCURRENCES:
                raise ValidationError(self.env._(
                    "The number of repetitions must be between 1 and %s.", MAX_OCCURRENCES))

    @api.depends('repeat_interval', 'repeat_unit', 'repeat_type', 'repeat_until', 'repeat_count')
    def _compute_display_name(self):
        units = dict(self._fields['repeat_unit']._description_selection(self.env))
        for recurrence in self:
            if recurrence.repeat_type == 'until':
                end = self.env._("until %s", recurrence.repeat_until or '')
            else:
                end = self.env._("%s times", recurrence.repeat_count)
            recurrence.display_name = self.env._(
                "Every %(interval)s %(unit)s, %(end)s",
                interval=recurrence.repeat_interval, unit=units.get(recurrence.repeat_unit, ''), end=end)

    def _get_delta(self, index):
        self.ensure_one()
        value = self.repeat_interval * index
        return relativedelta(**{f'{self.repeat_unit}s': value})

    def _generate_slots(self, slot):
        """ Create the next occurrences of ``slot`` (the first one of the series). """
        self.ensure_one()
        values_list = []
        index = 1
        while index < MAX_OCCURRENCES:
            delta = self._get_delta(index)
            start = slot.start_datetime + delta
            if self.repeat_type == 'count' and index >= self.repeat_count:
                break
            if self.repeat_type == 'until' and start.date() > self.repeat_until:
                break
            values = slot.copy_data({
                'start_datetime': start,
                'end_datetime': slot.end_datetime + delta,
                'recurrence_id': self.id,
                'state': slot.state,
            })[0]
            values_list.append(values)
            index += 1
        return self.env['om.planning.slot'].with_context(om_planning_no_recurrence=True).create(values_list)
