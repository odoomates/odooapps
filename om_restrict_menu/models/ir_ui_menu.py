# load_menus() and load_menus_root() are cached per user, not per company: the hidden menus are
# taken out of a copy of their result, never in _load_menus_blacklist() or get_user_roots(), which
# they call inside their cache.
from odoo import api, fields, models
from odoo.http import request

SETTINGS_MENU = 'base.menu_administration'


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    om_hidden_user_ids = fields.Many2many(
        'res.users', 'om_restrict_menu_user_rel', 'menu_id', 'user_id', string='Hidden for Users',
        groups='base.group_system',
        help="The menu and its sub-menus are hidden for these users, in every company.")
    om_hidden_company_ids = fields.Many2many(
        'res.company', 'om_restrict_menu_company_rel', 'menu_id', 'company_id', string='Hidden in Companies',
        groups='base.group_system',
        help="The menu and its sub-menus are hidden for every user while one of these companies "
             "is the current company.")

    @api.model
    def load_menus(self, debug):
        menus = super().load_menus(debug)
        hidden = self._om_hidden_menu_ids()
        return self._om_prune(menus, hidden) if hidden else menus

    @api.model
    def load_menus_root(self):
        root = super().load_menus_root()
        # the hidden roots are taken out above the modules that cache it again, see _register_hook()
        if self.env.context.get('om_menus_unpruned'):
            return root
        return self._om_prune_roots(root)

    def _register_hook(self):
        """ website caches load_menus_root() again, per user, above this module: the roots hidden in the company
        asking first would stay hidden in the others. When a module above this one overrides load_menus_root(),
        the final class of the registry gets one more override, above all of them, that takes the hidden roots
        out of a cache holding the roots of every company. """
        super()._register_hook()
        cls = type(self)
        if 'load_menus_root' in vars(cls):
            return
        mro = cls.__mro__
        mine = next(index for index, klass in enumerate(mro) if klass.__module__ == __name__)
        if any('load_menus_root' in vars(klass) for klass in mro[:mine]):
            cls.load_menus_root = _load_menus_root_above_caches

    @api.model
    def _om_prune_roots(self, root):
        """ A copy of the root of load_menus_root() without the hidden apps; ``root`` is never changed. """
        hidden = self._om_hidden_menu_ids()
        if not hidden:
            return root
        children = [menu for menu in root['children'] if menu['id'] not in hidden]
        return dict(root, children=children, all_menu_ids=[menu['id'] for menu in children])

    @api.model
    def _om_current_company(self):
        """ The menus request carries no context: the company switcher keeps the active companies
        in the cids cookie, the current one first. """
        if request and 'allowed_company_ids' not in self.env.context:
            current = (request.httprequest.cookies.get('cids') or '').replace(',', '-').split('-')[0]
            if current.isdigit() and int(current) in self.env.user.company_ids.ids:
                return self.env['res.company'].browse(int(current))
        return self.env.company

    @api.model
    def _om_hidden_menu_ids(self):
        """ The menus hidden for the user and in the current company. The administrators always
        keep the Settings app, so that no rule can lock them out of this one. """
        user = self.env.user.sudo()
        hidden = set(user.om_hidden_menu_ids._ids) | set(self._om_current_company().sudo().om_hidden_menu_ids._ids)
        if hidden and user._is_system():
            settings = self.env.ref(SETTINGS_MENU, raise_if_not_found=False)
            if settings:
                hidden -= set(self.sudo().with_context(active_test=False).search(
                    [('id', 'child_of', settings.id)])._ids)
        return hidden

    @api.model
    def _om_prune(self, menus, hidden):
        """ A copy of the menus of load_menus() without the hidden ones, their sub-menus and the
        folders they leave empty, as Odoo drops a folder that opens nothing. ``menus`` is the
        cached dict and is never changed. """
        pruned = {}

        def keep(menu_id):
            menu = menus[menu_id]
            children = [child for child in menu['children'] if child not in hidden and keep(child)]
            if menu['id'] and not children and not menu['action']:
                return False
            pruned[menu_id] = menu if children == menu['children'] else dict(menu, children=children)
            return True

        keep('root')
        return pruned


@api.model
def _load_menus_root_above_caches(self):
    """ load_menus_root() of the final class of the registry, set by IrUiMenu._register_hook() """
    root = super(type(self), self.with_context(om_menus_unpruned=True)).load_menus_root()
    return self._om_prune_roots(root)
