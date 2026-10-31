from markupsafe import Markup

from odoo import _, api, fields, models

from .ir_ui_menu import SETTINGS_MENU


class ResUsers(models.Model):
    _inherit = 'res.users'

    om_hidden_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_restrict_menu_user_rel', 'user_id', 'menu_id', string='Hidden Menus',
        groups='base.group_system',
        help="These menus and their sub-menus are hidden for the user, in every company.")
    om_visible_menu_ids = fields.Many2many(
        'ir.ui.menu', 'om_restrict_menu_visible_rel', 'user_id', 'menu_id', string='Visible Apps',
        domain=[('parent_id', '=', False)], groups='base.group_system',
        help="When set, the user sees these apps only, in every company: every other app, also one installed "
             "later, is hidden. The Hidden Menus still hide menus inside these apps.")
    om_home_action_hidden = fields.Boolean(
        compute='_compute_om_home_action_hidden', groups='base.group_system',
        help="The Home Action of the user opens only from hidden menus in the default company of the user: the "
             "first visible app opens instead.")

    om_hidden_menus_summary = fields.Html(
        string='Everything Hidden for the User', compute='_compute_om_hidden_menus_summary', sanitize=False,
        groups='base.group_system',
        help="Every menu hidden for the user, and why: hidden for the user, in one of their companies, or out of "
             "their Visible Apps.")

    @api.depends('action_id', 'om_hidden_menu_ids', 'om_visible_menu_ids', 'company_id', 'groups_id')
    def _compute_om_home_action_hidden(self):
        Menu = self.env['ir.ui.menu']
        system = self.env.ref('base.group_system')
        for user in self:
            hidden = Menu._om_hidden_menu_ids_for(user, user.company_id.sudo(), system in user._om_all_groups())
            user.om_home_action_hidden = Menu._om_action_hidden(user.action_id, hidden)

    @api.depends('om_hidden_menu_ids', 'om_visible_menu_ids', 'company_ids', 'groups_id')
    def _compute_om_hidden_menus_summary(self):
        Menu = self.env['ir.ui.menu'].sudo()
        system = self.env.ref('base.group_system')
        settings = self.env.ref(SETTINGS_MENU, raise_if_not_found=False)
        settings_ids = set(Menu.with_context(active_test=False).search(
            [('id', 'child_of', settings.id)]).ids) if settings else set()
        roots = Menu.search([('parent_id', '=', False)])
        for user in self:
            rows = [(menu, _('Hidden for the user, in every company')) for menu in user.om_hidden_menu_ids._origin]
            visible_apps = user.om_visible_menu_ids._origin
            if visible_apps:
                # the apps the groups of the user would show, a user not saved yet has no menus to compare with
                allowed = (Menu.with_user(user._origin)._visible_menu_ids() if user._origin.id
                           else set(roots.ids))
                rows += [(app, _('Not in the Visible Apps')) for app in roots - visible_apps if app.id in allowed]
            for company in user.company_ids._origin.sudo():
                rows += [(menu, _('Hidden in %s, while it is the current company', company.name))
                         for menu in company.om_hidden_menu_ids]
            user.om_hidden_menus_summary = self._om_summary_table(
                rows, settings_ids if system in user._om_all_groups() else set())

    def _om_all_groups(self):
        """ The groups of the user and the groups they imply, also on a form not saved yet. """
        self.ensure_one()
        return self.groups_id | self.groups_id.trans_implied_ids

    @api.model
    def _om_summary_table(self, rows, kept_ids):
        """ The rows (menu, why it is hidden) as a table; the menus in ``kept_ids`` stay visible all the same. """
        if not rows:
            return Markup('<p class="text-muted">%s</p>') % _('Nothing is hidden for this user.')
        kept = _('Kept all the same: administrators always keep the Settings app.')
        lines = Markup().join(
            Markup('<tr%s><td>%s</td><td>%s</td></tr>') % (
                Markup(' class="text-muted"') if menu.id in kept_ids else Markup(),
                menu.complete_name, kept if menu.id in kept_ids else why)
            for menu, why in sorted(rows, key=lambda row: row[0].complete_name or ''))
        return Markup('<table class="table table-sm"><thead><tr><th>%s</th><th>%s</th></tr></thead>'
                      '<tbody>%s</tbody></table>') % (_('Menu'), _('Why'), lines)
