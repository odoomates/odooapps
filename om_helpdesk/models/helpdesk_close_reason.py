from odoo import fields, models


class OmHelpdeskCloseReason(models.Model):
    _name = 'om.helpdesk.close.reason'
    _description = 'Helpdesk Close Reason'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
