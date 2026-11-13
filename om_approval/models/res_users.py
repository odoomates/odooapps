from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    approval_substitute_id = fields.Many2one(
        'res.users', domain=[('share', '=', False)],
        help='Who approves for you when you are away: the substitute suggested for your delegations.')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['approval_substitute_id']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['approval_substitute_id']
