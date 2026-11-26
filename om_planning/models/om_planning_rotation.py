from odoo import api, fields, models


class OmPlanningRotation(models.Model):
    _name = 'om.planning.rotation'
    _description = "Planning Rotation"
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    line_ids = fields.One2many('om.planning.rotation.line', 'rotation_id', string="Cycle", copy=True)
    cycle_length = fields.Integer(compute='_compute_cycle_length', string="Cycle Length (days)")
    role_id = fields.Many2one('om.planning.role', string="Role",
                              help="Role of the slots, when the template has none.")
    company_id = fields.Many2one('res.company', string="Company")
    note = fields.Text(string="Description")

    @api.depends('line_ids')
    def _compute_cycle_length(self):
        for rotation in self:
            rotation.cycle_length = len(rotation.line_ids)

    def action_apply(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Apply Rotation"),
            'res_model': 'om.planning.rotation.apply',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_rotation_id': self.id},
        }


class OmPlanningRotationLine(models.Model):
    _name = 'om.planning.rotation.line'
    _description = "Planning Rotation Day"
    _order = 'rotation_id, sequence, id'

    rotation_id = fields.Many2one('om.planning.rotation', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    day_number = fields.Integer(compute='_compute_day_number', string="Day")
    template_id = fields.Many2one('om.planning.template', string="Template",
                                  help="Leave empty for a day off.")
    is_day_off = fields.Boolean(compute='_compute_day_number', string="Day Off")

    @api.depends('rotation_id.line_ids', 'sequence', 'template_id')
    def _compute_day_number(self):
        for rotation in self.rotation_id:
            for index, line in enumerate(rotation.line_ids.sorted(lambda l: (l.sequence, l.id or 0))):
                if line in self:
                    line.day_number = index + 1
        for line in self:
            if not line.rotation_id:
                line.day_number = 0
            line.is_day_off = not line.template_id
