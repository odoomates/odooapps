# Seeds model rules from the models reachable through the menus a profile
# leaves visible.
from odoo import _, api, fields, models

ACTION_MODEL_FIELD = {
    'ir.actions.act_window': 'res_model',
    'ir.actions.report': 'model',
    'ir.actions.server': 'model_name',
}


class OmAccessLoadModels(models.TransientModel):
    _name = 'om.access.load.models'
    _description = 'Load Models into an Access Profile'

    profile_id = fields.Many2one(
        'om.access.profile', required=True, ondelete='cascade')
    menu_ids = fields.Many2many(
        'ir.ui.menu', string='Limit to Menus',
        help="Left empty, every menu the profile still shows is considered.")
    readonly = fields.Boolean(
        string='Create them Read Only', default=False,
        help="Create the rows with Edit, Create and Delete already cleared.")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'profile_id' in fields_list and self.env.context.get('active_model') == 'om.access.profile':
            values.setdefault('profile_id', self.env.context.get('active_id'))
        return values

    def _candidate_models(self):
        self.ensure_one()
        Menu = self.env['ir.ui.menu'].sudo()
        menus = self.menu_ids.sudo() or Menu.search([])
        hidden = self.profile_id.hidden_menu_ids
        if hidden:
            menus -= Menu.search([('id', 'child_of', hidden.ids)])

        names = set()
        for menu in menus:
            action = menu.sudo().action
            if not action:
                continue
            field_name = ACTION_MODEL_FIELD.get(action._name)
            if not field_name:
                continue
            model_name = action[field_name]
            if model_name and model_name in self.env:
                names.add(model_name)
        return names

    def action_load(self):
        self.ensure_one()
        profile = self.profile_id
        existing = set(profile.model_ids.mapped('model_id.model'))
        wanted = self._candidate_models() - existing
        if not wanted:
            return {'type': 'ir.actions.act_window_close'}
        models_by_name = {
            record.model: record.id
            for record in self.env['ir.model'].sudo().search([('model', 'in', list(wanted))])
        }
        permissions = {} if not self.readonly else {
            'perm_write': False, 'perm_create': False, 'perm_unlink': False,
        }
        self.env['om.access.profile.model'].create([
            dict(permissions, profile_id=profile.id, model_id=model_id)
            for model_id in sorted(models_by_name.values())
        ])
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.access.profile',
            'res_id': profile.id,
            'view_mode': 'form',
            'target': 'current',
            'name': _('Access Profile'),
        }
