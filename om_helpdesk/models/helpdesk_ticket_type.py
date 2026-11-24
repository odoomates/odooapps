from odoo import fields, models


class OmHelpdeskTicketType(models.Model):
    _name = 'om.helpdesk.ticket.type'
    _description = 'Helpdesk Ticket Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('unique (name)', 'A ticket type with this name already exists.')
