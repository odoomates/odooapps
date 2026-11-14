from odoo import models

from .om_adapt_rule import ROOT_MENU


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def load_web_menus(self, debug):
        """ Put the menus in the order learnt for the current user.

        The menus are put in order once each app knows the screen it opens on, so an app
        still opens where it always did; the menus themselves are not written to.
        """
        menus = super().load_web_menus(debug)
        if 'om.adapt.rule' not in self.env:
            return menus
        for parent, order in self.env['om.adapt.rule']._om_menu_orders().items():
            key = 'root' if parent == ROOT_MENU else int(parent) if parent.isdigit() else None
            if key not in menus:
                continue
            children = menus[key]['children']
            position = {menu_id: index for index, menu_id in enumerate(order)}
            # the lists come from a cache: a new list, never the cached one changed
            menus[key] = dict(menus[key], children=sorted(
                children, key=lambda menu_id: (position.get(menu_id, len(order)), children.index(menu_id))))
        return menus
