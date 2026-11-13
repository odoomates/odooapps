from odoo import fields, models


class PatientTag(models.Model):
    _name = 'patient.tag'
    _description = 'Patient Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer()
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint('unique (name)', "A tag with this name already exists.")
