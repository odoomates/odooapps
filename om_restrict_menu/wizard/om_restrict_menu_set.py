from odoo import Command, api, fields, models


class OmRestrictMenuSet(models.TransientModel):
    """ Set the Hidden Menus and the Visible Apps of several users at once, typed in or taken from another
    user. """
    _name = 'om.restrict.menu.set'
    _description = 'Set the Hidden Menus of Users'

    user_ids = fields.Many2many(
        'res.users', 'om_restrict_menu_set_user_rel', 'wizard_id', 'user_id', string='Users', required=True,
        domain=[('share', '=', False)], default=lambda self: self._default_user_ids())
    source_user_id = fields.Many2one(
        'res.users', string='Copy From', domain=[('share', '=', False)],
        help='Fills in the hidden menus and the visible apps of this user.')
    hidden_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_restrict_menu_set_hidden_rel', 'wizard_id', 'menu_id', string='Hidden Menus',
        compute='_compute_menus', store=True, readonly=False)
    visible_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_restrict_menu_set_visible_rel', 'wizard_id', 'menu_id', string='Visible Apps',
        domain=[('parent_id', '=', False)], compute='_compute_menus', store=True, readonly=False,
        help='When set, the users see these apps only.')
    mode = fields.Selection(
        [('replace', 'Replace'), ('add', 'Add')], string='Apply', required=True, default='replace',
        help='Replace: the users get exactly these hidden menus and visible apps. Add: they are added to those '
             'of each user.')

    @api.model
    def _default_user_ids(self):
        if self.env.context.get('active_model') == 'res.users':
            return [Command.set(self.env.context.get('active_ids') or [])]
        return False

    @api.depends('source_user_id')
    def _compute_menus(self):
        for wizard in self:
            if wizard.source_user_id:
                wizard.hidden_menu_ids = wizard.source_user_id.om_hidden_menu_ids
                wizard.visible_menu_ids = wizard.source_user_id.om_visible_menu_ids

    def action_apply(self):
        self.ensure_one()
        if self.mode == 'replace':
            values = {'om_hidden_menu_ids': [Command.set(self.hidden_menu_ids.ids)],
                      'om_visible_menu_ids': [Command.set(self.visible_menu_ids.ids)]}
        else:
            values = {'om_hidden_menu_ids': [Command.link(menu.id) for menu in self.hidden_menu_ids],
                      'om_visible_menu_ids': [Command.link(menu.id) for menu in self.visible_menu_ids]}
        (self.user_ids - self.source_user_id).write(values)
        return {'type': 'ir.actions.act_window_close'}
