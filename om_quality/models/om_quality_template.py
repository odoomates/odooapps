from odoo import api, fields, models
from odoo.exceptions import ValidationError

TEST_KINDS = [
    ('passfail', 'Pass / Fail'),
    ('measure', 'Measure'),
]


class OmQualityTestTemplate(models.Model):
    _name = 'om.quality.test.template'
    _description = 'Quality Inspection Template'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', index=True)
    description = fields.Text(translate=True, help="Shown to the operator above the parameters.")
    parameter_ids = fields.One2many('om.quality.test.parameter', 'template_id', string='Parameters', copy=True)
    parameter_count = fields.Integer(compute='_compute_parameter_count', string='Parameters Count')

    @api.depends('parameter_ids')
    def _compute_parameter_count(self):
        for template in self:
            template.parameter_count = len(template.parameter_ids)


class OmQualityTestParameter(models.Model):
    _name = 'om.quality.test.parameter'
    _description = 'Quality Inspection Parameter'
    _order = 'sequence, id'

    template_id = fields.Many2one('om.quality.test.template', string='Template', required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Parameter', required=True, translate=True)
    test_kind = fields.Selection(TEST_KINDS, string='Kind', required=True, default='measure')
    norm_min = fields.Float(string='Minimum', digits='Quality Measure')
    norm_target = fields.Float(string='Target', digits='Quality Measure')
    norm_max = fields.Float(string='Maximum', digits='Quality Measure')
    uom_id = fields.Many2one('uom.uom', string='Unit')
    samples = fields.Integer(default=1, help="How many values the operator records for this parameter.")
    instructions = fields.Char(translate=True)

    @api.constrains('norm_min', 'norm_max', 'samples', 'test_kind')
    def _check_limits(self):
        for parameter in self:
            if parameter.samples < 1:
                raise ValidationError(self.env._("A parameter needs at least one sample."))
            if parameter.test_kind == 'measure' and parameter.norm_min > parameter.norm_max:
                raise ValidationError(self.env._(
                    "The minimum of %s is above its maximum.", parameter.name))
