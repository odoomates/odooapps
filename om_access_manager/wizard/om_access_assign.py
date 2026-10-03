# Set the access profiles of several users at once, from the Users list.
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OmAccessAssign(models.TransientModel):
    _name = 'om.access.assign'
    _description = 'Set Access Profiles'

    user_ids = fields.Many2many('res.users', string='Users', required=True)
    profile_ids = fields.Many2many('om.access.profile', string='Access Profiles')
    mode = fields.Selection([
        ('add', 'Add these profiles'),
        ('remove', 'Remove these profiles'),
        ('replace', 'Replace all their profiles with these'),
    ], string='What to Do', default='add', required=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'user_ids' in fields_list and self.env.context.get('active_model') == 'res.users':
            values.setdefault('user_ids', [(6, 0, self.env.context.get('active_ids') or [])])
        return values

    def action_apply(self):
        self.ensure_one()
        if self.mode != 'replace' and not self.profile_ids:
            raise UserError(_("Pick the profiles to add or to remove."))
        if self.mode == 'add':
            command = [(4, profile.id) for profile in self.profile_ids]
        elif self.mode == 'remove':
            command = [(3, profile.id) for profile in self.profile_ids]
        else:
            command = [(6, 0, self.profile_ids.ids)]
        self.user_ids.write({'access_profile_ids': command})
        return {'type': 'ir.actions.act_window_close'}
