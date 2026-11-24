from random import randint

from odoo import fields, models


class OmHelpdeskTag(models.Model):
    _name = 'om.helpdesk.tag'
    _description = 'Helpdesk Tag'
    _order = 'name'

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(default=_get_default_color)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique (name)', 'A tag with this name already exists.')
