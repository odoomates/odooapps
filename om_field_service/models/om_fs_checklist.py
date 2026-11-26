from odoo import api, fields, models


class OmFsChecklistLine(models.Model):
    _name = 'om.fs.checklist.line'
    _description = "Field Service Checklist Line"
    _order = 'sequence, id'

    task_id = fields.Many2one('project.task', string="Job", required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Item", required=True)
    check_type = fields.Selection([
        ('check', 'Check Box'),
        ('text', 'Text'),
        ('number', 'Number'),
    ], string="Type", required=True, default='check')
    required = fields.Boolean(string="Required")
    uom_label = fields.Char(string="Unit")
    value_check = fields.Boolean(string="Checked")
    value_text = fields.Char(string="Answer")
    value_number = fields.Float(string="Value")
    value_number_set = fields.Boolean(string="Value Entered")
    is_done = fields.Boolean(compute='_compute_is_done', store=True, string="Done")
    company_id = fields.Many2one(related='task_id.company_id', store=True, string="Company")

    @api.depends('check_type', 'value_check', 'value_text', 'value_number_set')
    def _compute_is_done(self):
        for line in self:
            if line.check_type == 'check':
                line.is_done = line.value_check
            elif line.check_type == 'text':
                line.is_done = bool((line.value_text or '').strip())
            else:
                line.is_done = line.value_number_set

    @api.onchange('value_number')
    def _onchange_value_number(self):
        self.value_number_set = True

    def _fs_display_value(self):
        self.ensure_one()
        if self.check_type == 'check':
            return self.env._("Yes") if self.value_check else self.env._("No")
        if self.check_type == 'text':
            return self.value_text or ''
        if not self.value_number_set:
            return ''
        value = ('%f' % self.value_number).rstrip('0').rstrip('.')
        return f'{value} {self.uom_label}'.strip() if self.uom_label else value

    def _fs_mobile_data(self):
        return [{
            'id': line.id,
            'name': line.name,
            'type': line.check_type,
            'required': line.required,
            'uom': line.uom_label or '',
            'check': line.value_check,
            'text': line.value_text or '',
            'number': line.value_number if line.value_number_set else '',
            'done': line.is_done,
        } for line in self]
