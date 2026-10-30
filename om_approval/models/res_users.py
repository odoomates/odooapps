from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    approval_substitute_id = fields.Many2one(
        'res.users', domain=[('share', '=', False)], user_writeable=True,
        help='Who approves for you when you are away: the substitute suggested for your delegations.')
