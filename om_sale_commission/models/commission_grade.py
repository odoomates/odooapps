from odoo import fields, models


class OmCommissionGrade(models.Model):
    _name = 'om.commission.grade'
    _description = 'Reseller Grade'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    partner_ids = fields.One2many('res.partner', 'om_commission_grade_id', string='Resellers')
    partner_count = fields.Integer(compute='_compute_partner_count')

    def _compute_partner_count(self):
        data = dict(self.env['res.partner']._read_group(
            [('om_commission_grade_id', 'in', self.ids)], ['om_commission_grade_id'], ['__count']))
        for grade in self:
            grade.partner_count = data.get(grade, 0)
