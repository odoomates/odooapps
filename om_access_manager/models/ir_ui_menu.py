# Menus are filtered in _load_menus_blacklist(), cached per user. Never filter in
# _visible_menu_ids(): it is cached per group set and would leak between users.
from odoo import api, models

SETTINGS_MENU = 'base.menu_administration'


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _load_menus_blacklist(self):
        result = super()._load_menus_blacklist()
        rules = self.env['om.access.profile']._current_rules()
        if not rules.enabled:
            return result
        hidden = set(rules.menu_blacklist())
        if rules.has_flag('hide_settings_menu'):
            settings = self.env.ref(SETTINGS_MENU, raise_if_not_found=False)
            if settings:
                hidden |= set(self.sudo().with_context(active_test=False, **{'ir.ui.menu.full_list': True}).search(
                    [('id', 'child_of', settings.id)]
                )._ids)
        return result + list(hidden)

    @api.model
    def get_user_roots(self):
        # Odoo 16 leaves the apps out of the blacklist of load_menus(): a hidden
        # app would stay on the home screen
        roots = super().get_user_roots()
        blacklist = set(self._load_menus_blacklist())
        return roots.filtered(lambda menu: menu.id not in blacklist) if blacklist else roots
