<<<<<<< HEAD
# load_menus() and load_menus_root() are cached per user, not per company: the hidden menus are
# taken out of a copy of their result, never in _load_menus_blacklist() or get_user_roots(), which
# they call inside their cache.
from odoo import api, fields, models
from odoo.http import request
=======
# -*- coding: utf-8 -*-
# load_menus() and load_menus_root() are cached per user, not per company: the hidden menus are
# taken out of a copy of their result, never in _visible_menu_ids() or get_user_roots(), which
# they call inside their cache.
from odoo import api, fields, models

from . import compat
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

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
    om_visible_user_ids = fields.Many2many(
        'res.users', 'om_restrict_menu_visible_rel', 'menu_id', 'user_id', string='Visible App of Users',
        groups='base.group_system',
        help="An app in the Visible Apps of these users: they see it, and no app out of their Visible Apps.")

    @api.model
    def load_menus(self, debug):
<<<<<<< HEAD
        menus = super().load_menus(debug)
        hidden = self._om_hidden_menu_ids()
        return self._om_prune(menus, hidden) if hidden else menus

    @api.model
    def load_menus_root(self):
        root = super().load_menus_root()
        # the hidden roots are taken out above the modules that cache it again, see _register_hook()
=======
        menus = super(IrUiMenu, self).load_menus(debug)
        # the hidden menus are taken out above the modules that cache it again, see _register_hook()
        if self.env.context.get('om_menus_unpruned'):
            return menus
        return self._om_prune(menus)

    @api.model
    def load_menus_root(self):
        root = super(IrUiMenu, self).load_menus_root()
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
        if self.env.context.get('om_menus_unpruned'):
            return root
        return self._om_prune_roots(root)

    def _register_hook(self):
<<<<<<< HEAD
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
=======
        """ Other modules cache load_menus() or load_menus_root() again, per user, above this module (web_tour
        caches load_menus() in Odoo 10): the menus hidden in the company asking first would stay hidden in the
        others. When a module above this one overrides one of them, the final class of the registry gets one
        more override, above all of them, that takes the hidden menus out of a cache holding the menus of
        every company. """
        super(IrUiMenu, self)._register_hook()
        cls = type(self)
        mro = cls.__mro__
        mine = next(index for index, klass in enumerate(mro) if klass.__module__ == __name__)
        for name, method in (('load_menus', _load_menus_above_caches),
                             ('load_menus_root', _load_menus_root_above_caches)):
            if name not in vars(cls) and any(name in vars(klass) for klass in mro[:mine]):
                setattr(cls, name, method)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

    @api.model
    def _om_prune_roots(self, root):
        """ A copy of the root of load_menus_root() without the hidden apps; ``root`` is never changed. """
        hidden = self._om_hidden_menu_ids()
        if not hidden:
            return root
        children = [menu for menu in root['children'] if menu['id'] not in hidden]
        return dict(root, children=children, all_menu_ids=[menu['id'] for menu in children])

    @api.model
<<<<<<< HEAD
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
        """ The menus hidden for the user and in the current company. """
        user = self.env.user.sudo()
        return self._om_hidden_menu_ids_for(user, self._om_current_company().sudo(), user._is_system())
=======
    def _om_hidden_menu_ids(self):
        """ The menus hidden for the user and in the current company. """
        user = self.env.user.sudo()
        return self._om_hidden_menu_ids_for(user, compat.current_company(self.env).sudo(), self._om_is_system(user))

    @api.model
    def _om_is_system(self, user):
        return self.env.ref('base.group_system') in user.groups_id
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)

    @api.model
    def _om_hidden_menu_ids_for(self, user, company, is_system):
        """ The menus hidden for ``user`` while ``company`` is the current company: the menus hidden for the user
        and in the company, and the apps out of the Visible Apps of the user when they are set. The administrators
        always keep the Settings app, so that no rule can lock them out of this one. ``user`` may be the record
        of a form not saved yet. """
<<<<<<< HEAD
        hidden = set(user.om_hidden_menu_ids._origin.ids) | set(company.om_hidden_menu_ids.ids)
        visible_apps = user.om_visible_menu_ids._origin
=======
        hidden = set(compat.origin(user.om_hidden_menu_ids).ids) | set(company.om_hidden_menu_ids.ids)
        visible_apps = compat.origin(user.om_visible_menu_ids)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
        if visible_apps:
            hidden |= set(self.sudo().search([('parent_id', '=', False)]).ids) - set(visible_apps.ids)
        if hidden and is_system:
            settings = self.env.ref(SETTINGS_MENU, raise_if_not_found=False)
            if settings:
                hidden -= set(self.sudo().with_context(active_test=False).search(
<<<<<<< HEAD
                    [('id', 'child_of', settings.id)])._ids)
=======
                    [('id', 'child_of', settings.id)]).ids)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
        return hidden

    @api.model
    def _om_action_hidden(self, action, hidden):
        """ Whether ``action`` opens from menus that are all hidden, themselves or one of their parents. An
        action opened from no menu is not hidden. """
        if not action or not hidden:
            return False
<<<<<<< HEAD
        menus = self.sudo().search([('action', '=', f'{action.type},{action.id}')])
        return bool(menus) and all(
            hidden.intersection(int(menu_id) for menu_id in menu.parent_path.split('/') if menu_id)
            for menu in menus)

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
=======
        Menu = self.sudo().with_context(active_test=False)
        menus = Menu.search([('action', '=', '%s,%s' % (action.type, action.id))])
        if not menus:
            return False
        under_hidden = set(Menu.search([('id', 'child_of', list(hidden))]).ids)
        return all(menu.id in under_hidden for menu in menus)

    @api.model
    def _om_prune(self, root):
        """ A copy of the menu tree of load_menus() without the hidden menus, their sub-menus and the folders
        they leave empty, as a folder that opens nothing has nothing to show. ``root`` is the cached tree and
        is never changed. """
        hidden = self._om_hidden_menu_ids()
        if not hidden:
            return root

        def prune(menu):
            old = menu.get('children') or []
            children = []
            for child in old:
                if child['id'] in hidden:
                    continue
                kept = prune(child)
                if kept is not None:
                    children.append(kept)
            if menu['id'] and not children and not menu.get('action'):
                return None
            if len(children) == len(old) and all(new is child for new, child in zip(children, old)):
                return menu
            return dict(menu, children=children)

        pruned = prune(root) or dict(root, children=[])
        ids = []

        def collect(menu):
            for child in menu.get('children') or []:
                ids.append(child['id'])
                collect(child)

        collect(pruned)
        return dict(pruned, all_menu_ids=ids)


@api.model
def _load_menus_above_caches(self, debug):
    """ load_menus() of the final class of the registry, set by IrUiMenu._register_hook() """
    menus = super(type(self), self.with_context(om_menus_unpruned=True)).load_menus(debug)
    return self._om_prune(menus)
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)


@api.model
def _load_menus_root_above_caches(self):
    """ load_menus_root() of the final class of the registry, set by IrUiMenu._register_hook() """
    root = super(type(self), self.with_context(om_menus_unpruned=True)).load_menus_root()
    return self._om_prune_roots(root)
