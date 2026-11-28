from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def om_launcher_creatable(self, menu_ids):
        """ :return: the ids, among `menu_ids`, of the menus visible to the user that open a model with a
        form view on which the user may create records: the launcher offers New on them. """
        menus = self.browse(menu_ids).exists()._filter_visible_menus()
        creatable = []
        for menu in menus:
            action = menu.sudo().action
            if not action or action._name != 'ir.actions.act_window' or action.res_model not in self.env:
                continue
            if action.target == 'new':
                continue  # a wizard, opened in a dialog: there is no list to come back to
            if 'form' not in (action.view_mode or '').split(','):
                continue
            if self.env[action.res_model].has_access('create'):
                creatable.append(menu.id)
        return creatable

    @api.model
    def om_launcher_english_names(self):
        """ :return: {menu id: English name} of the menus visible to the user, so the launcher finds a menu
        by its English name too when the user works in another language. """
        menus = self.with_context(lang='en_US').search([('action', '!=', False)])
        return {menu.id: menu.name for menu in menus}
