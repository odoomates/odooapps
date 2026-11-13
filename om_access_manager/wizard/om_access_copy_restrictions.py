# Copies the rules of one profile into another: a restriction only bites when
# every additive profile of the user carries it.
from odoo import _, api, fields, models
from odoo.exceptions import UserError

COPIED = (
    ('model_ids', 'om.access.profile.model', ('model_id',)),
    ('menu_rule_ids', 'om.access.profile.menu', ('menu_id',)),
    ('field_ids', 'om.access.profile.field', ('field_id',)),
    ('button_ids', 'om.access.profile.button',
     ('model_id', 'view_type', 'button_type', 'button_name', 'button_id')),
    ('element_ids', 'om.access.profile.element',
     ('model_id', 'element_type', 'element_name')),
)


class OmAccessCopyRestrictions(models.TransientModel):
    _name = 'om.access.copy.restrictions'
    _description = 'Copy the Restrictions of an Access Profile'

    profile_id = fields.Many2one(
        'om.access.profile', string='Into', required=True, ondelete='cascade')
    source_id = fields.Many2one(
        'om.access.profile', string='From', required=True, ondelete='cascade')
    copy_models = fields.Boolean(string='Models', default=True)
    copy_fields = fields.Boolean(string='Fields', default=True)
    copy_buttons = fields.Boolean(string='Buttons', default=True)
    copy_elements = fields.Boolean(string='Tabs, Filters and Views', default=True)
    copy_menus = fields.Boolean(string='Menus', default=True,
                                help="The hidden menus and the rights set on menus.")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'profile_id' in fields_list and self.env.context.get('active_model') == 'om.access.profile':
            values.setdefault('profile_id', self.env.context.get('active_id'))
        return values

    @api.constrains('profile_id', 'source_id')
    def _check_not_itself(self):
        for wizard in self:
            if wizard.profile_id == wizard.source_id:
                raise UserError(_("Pick a profile other than the one you are filling."))

    def action_copy(self):
        self.ensure_one()
        wanted = {
            'model_ids': self.copy_models,
            'menu_rule_ids': self.copy_menus,
            'field_ids': self.copy_fields,
            'button_ids': self.copy_buttons,
            'element_ids': self.copy_elements,
        }
        for field_name, model_name, keys in COPIED:
            if not wanted[field_name]:
                continue
            existing = {
                tuple(line[key].id if hasattr(line[key], 'id') else line[key] for key in keys)
                for line in self.profile_id[field_name]
            }
            values = []
            for line in self.source_id[field_name]:
                key = tuple(line[k].id if hasattr(line[k], 'id') else line[k] for k in keys)
                if key in existing:
                    continue
                copied = line.copy_data()[0]
                copied['profile_id'] = self.profile_id.id
                values.append(copied)
            if values:
                self.env[model_name].create(values)
        if self.copy_menus:
            self.profile_id.hidden_menu_ids |= self.source_id.hidden_menu_ids
        return {'type': 'ir.actions.act_window_close'}
