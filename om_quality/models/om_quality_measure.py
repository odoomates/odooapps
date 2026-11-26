from odoo import api, fields, models
from odoo.tools import float_compare, float_repr

from .om_quality_template import TEST_KINDS


class OmQualityMeasureLine(models.Model):
    _name = 'om.quality.measure.line'
    _description = 'Quality Measure'
    _order = 'check_id, sequence, id'

    check_id = fields.Many2one('om.quality.check', string='Check', required=True, index=True, ondelete='cascade')
    parameter_id = fields.Many2one('om.quality.test.parameter', string='Parameter', index='btree_not_null')
    name = fields.Char(string='Measure', required=True)
    sequence = fields.Integer(default=10)
    sample = fields.Integer(default=1)
    test_kind = fields.Selection(TEST_KINDS, string='Kind', required=True, default='measure')
    norm_min = fields.Float(string='Minimum', digits='Quality Measure')
    norm_target = fields.Float(string='Target', digits='Quality Measure')
    norm_max = fields.Float(string='Maximum', digits='Quality Measure')
    uom_id = fields.Many2one('uom.uom', string='Unit')
    instructions = fields.Char()
    value = fields.Float(digits='Quality Measure', aggregator='avg')
    value_set = fields.Boolean(string='Recorded')
    result = fields.Selection([('pass', 'Pass'), ('fail', 'Fail')])
    is_ok = fields.Boolean(string='In Limits', compute='_compute_is_ok', store=True)
    deviation = fields.Float(compute='_compute_is_ok', store=True, digits='Quality Measure', aggregator='avg',
                             help="Value minus target.")

    check_state = fields.Selection(related='check_id.state', string='Check Status', store=True)
    point_id = fields.Many2one(related='check_id.point_id', string='Control Point', store=True, index=True)
    product_id = fields.Many2one(related='check_id.product_id', string='Product', store=True, index=True)
    partner_id = fields.Many2one(related='check_id.partner_id', string='Partner', store=True)
    team_id = fields.Many2one(related='check_id.team_id', string='Team', store=True)
    company_id = fields.Many2one(related='check_id.company_id', string='Company', store=True, index=True)
    date_done = fields.Datetime(related='check_id.date_done', string='Done On', store=True)

    @api.depends('test_kind', 'value', 'value_set', 'result', 'norm_min', 'norm_max', 'norm_target')
    def _compute_is_ok(self):
        digits = self.env['decimal.precision'].precision_get('Quality Measure')
        for line in self:
            line.deviation = line.value - line.norm_target if line.test_kind == 'measure' and line.value_set else 0.0
            if line.test_kind == 'passfail':
                line.is_ok = line.result == 'pass'
            elif not line.value_set:
                line.is_ok = False
            elif not line.norm_min and not line.norm_max:
                line.is_ok = True
            else:
                line.is_ok = (float_compare(line.value, line.norm_min, precision_digits=digits) >= 0
                              and float_compare(line.value, line.norm_max, precision_digits=digits) <= 0)

    def _compute_display_name(self):
        for line in self:
            sample = f' #{line.sample}' if line.sample > 1 or len(line.check_id.measure_line_ids.filtered(
                lambda other: other.name == line.name)) > 1 else ''
            line.display_name = f'{line.name}{sample}'

    def _has_value(self):
        self.ensure_one()
        return bool(self.result) if self.test_kind == 'passfail' else self.value_set

    def _format_value(self):
        self.ensure_one()
        if self.test_kind == 'passfail':
            return dict(self._fields['result']._description_selection(self.env)).get(self.result, '')
        digits = self.env['decimal.precision'].precision_get('Quality Measure')
        text = float_repr(self.value, digits)
        return f'{text} {self.uom_id.name}' if self.uom_id else text

    def _dialog_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'sample': self.sample,
            'test_kind': self.test_kind,
            'norm_min': self.norm_min,
            'norm_target': self.norm_target,
            'norm_max': self.norm_max,
            'has_limits': bool(self.norm_min or self.norm_max),
            'uom': self.uom_id.name or '',
            'instructions': self.instructions or '',
            'value': self.value if self.value_set else '',
            'value_set': self.value_set,
            'result': self.result or '',
            'is_ok': self.is_ok,
        }
