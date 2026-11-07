from odoo import models


class ResUsers(models.Model):
    _name = 'res.users'
    _inherit = ['res.users', 'om.pos.access.rules']
