# The Access Manager app and its group: the access managers, not the Settings
# users, manage the profiles, and need nothing more than the group to do it.
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestAccessGroup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref('om_access_manager.group_access_manager')
        cls.app = cls.env.ref('om_access_manager.om_access_root_menu')
        cls.manager = new_test_user(cls.env, 'om_access_group_manager',
                                    groups='base.group_user,om_access_manager.group_access_manager')
        cls.settings_user = new_test_user(cls.env, 'om_access_group_settings', groups='base.group_system')
        cls.employee = new_test_user(cls.env, 'om_access_group_employee',
                                     groups='base.group_user,base.group_partner_manager')
        action = cls.env['ir.actions.act_window'].create({'name': 'Tags', 'res_model': 'res.partner.category'})
        cls.tags = cls.env['ir.ui.menu'].create({
            'name': 'OM Group Tags', 'action': f'ir.actions.act_window,{action.id}'})

    def _visible(self, user):
        return self.app.id in self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()

    def test_the_administrator_is_an_access_manager(self):
        self.assertIn(self.env.ref('base.user_admin'), self.group.all_user_ids)
        self.assertTrue(self._visible(self.env.ref('base.user_admin')))

    def test_the_app_and_the_profiles_are_for_the_group_only(self):
        self.assertTrue(self._visible(self.manager))
        self.assertFalse(self._visible(self.settings_user))
        self.assertFalse(self._visible(self.employee))
        with self.assertRaises(AccessError):
            self.env['om.access.profile'].with_user(self.settings_user).search([])
        with self.assertRaises(AccessError):
            self.env['om.access.profile'].with_user(self.settings_user).om_menu_tree()

    def test_an_access_manager_does_the_whole_job(self):
        """ Without being a Settings user: create a profile, set it from the
        menu tree, give it to users, check the result. """
        Profile = self.env['om.access.profile'].with_user(self.manager)
        self.assertTrue(Profile.om_menu_tree())
        profile = Profile.create({'name': 'By a Manager'})
        profile.om_menu_panel_set(self.tags.id, {'kind': 'data_rights', 'perm_create': False})
        profile.om_menu_panel_set(self.tags.id, {'kind': 'field', 'field': 'color', 'mode': 'hide'})
        self.env['om.access.assign'].with_user(self.manager).create({
            'user_ids': [(6, 0, self.employee.ids)], 'profile_ids': [(6, 0, profile.ids)], 'mode': 'add',
        }).action_apply()
        self.assertEqual(self.employee.sudo().access_profile_ids, profile)
        rules = self.env['om.access.profile'].with_user(self.employee)._current_rules()
        self.assertFalse(rules.allows('res.partner.category', 'create'))
        report = self.env['om.access.test.user'].with_user(self.manager).create({'user_id': self.employee.id}).report
        self.assertIn('By a Manager', report)
        wizard = self.env['om.access.template.wizard'].with_user(self.manager).create({
            'template_key': 'app_readonly', 'name': 'Read Only Contacts',
            'app_id': self.env.ref('base.menu_administration').id})
        self.assertTrue(wizard)

    def test_the_last_access_manager_is_kept(self):
        """ Taking the last access manager out of the group is refused once a
        profile would lock them out. """
        from unittest.mock import patch
        Profile = type(self.env['om.access.profile'])
        with patch.object(Profile, '_exempt_user_ids', lambda self: ()):
            managers = self.group.all_user_ids.filtered('active')
            self.env['om.access.profile'].create({
                'name': 'Locked', 'block_login': True, 'apply_to_admin': True,
                'user_ids': [(6, 0, (managers - self.manager).ids)]})
            with self.assertRaises(Exception):
                self.manager.group_ids = [(3, self.group.id)]

    def test_pages_filters_and_views_tabs(self):
        """ The three tabs show their kind of view element, and a line added on
        one of them is of that kind. They are developer mode tabs, which the
        web client hides, so the view is read rather than driven. """
        arch = self.env['om.access.profile'].get_view(view_type='form')['arch']
        for kind in ('view', 'page', 'filter'):
            self.assertIn(f"default_element_type': '{kind}'", arch)
        profile = self.env['om.access.profile'].create({'name': 'Tabs'})
        partner = self.env['ir.model']._get('res.partner')
        profile.with_context(default_element_type='view').view_element_ids = [
            (0, 0, {'model_id': partner.id, 'element_name': 'kanban'})]
        profile.with_context(default_element_type='page').page_element_ids = [
            (0, 0, {'model_id': partner.id, 'element_name': 'internal_notes'})]
        self.assertEqual(profile.view_element_ids.element_type, 'view')
        self.assertEqual(profile.page_element_ids.element_name, 'internal_notes')
        self.assertEqual(set(profile.element_ids.mapped('element_type')), {'view', 'page'})
        self.assertFalse(profile.filter_element_ids)

    def test_the_menu_tree_leaves_the_app_out(self):
        menu_ids = {menu['id'] for menu in self.env['om.access.profile'].om_menu_tree()}
        app_menus = self.env['ir.ui.menu'].search([('id', 'child_of', self.app.id)])
        self.assertFalse(menu_ids & set(app_menus.ids))
        self.assertIn(self.tags.id, menu_ids)

    def _app_with_its_group(self):
        privilege = self.env['res.groups.privilege'].create({'name': 'OM Buying'})
        user_group = self.env['res.groups'].create({
            'name': 'User', 'privilege_id': privilege.id, 'implied_ids': [(4, self.env.ref('base.group_user').id)]})
        self.env['res.groups'].create({
            'name': 'Administrator', 'privilege_id': privilege.id, 'implied_ids': [(4, user_group.id)]})
        app = self.env['ir.ui.menu'].create({'name': 'OM Buying', 'group_ids': [(6, 0, user_group.ids)]})
        self.env['ir.ui.menu'].create({'name': 'Orders', 'parent_id': app.id,
                                       'action': f'ir.actions.act_window,{self.tags.action.id}'})
        return privilege, user_group, app

    def test_a_profile_opens_an_app(self):
        """ The user form leaves the app empty; the profile grants it. """
        privilege, user_group, app = self._app_with_its_group()
        Menu = self.env['ir.ui.menu']
        self.assertNotIn(app.id, Menu.with_user(self.employee)._visible_menu_ids())
        profile = self.env['om.access.profile'].with_user(self.manager).create({
            'name': 'Buyer', 'user_ids': [(6, 0, self.employee.ids)]})
        panel = profile.om_menu_panel(app.id)
        self.assertEqual([(grant['name'], [g['name'] for g in grant['groups']], grant['granted'])
                          for grant in panel['grants']],
                         [('OM Buying', ['User', 'Administrator'], False)])
        panel = profile.om_menu_panel_set(app.id, {'kind': 'grant', 'privilege_id': privilege.id,
                                                   'group_id': user_group.id})
        self.assertEqual(panel['grants'][0]['granted'], user_group.id)
        self.env.invalidate_all()
        self.assertIn(user_group, self.employee.all_group_ids)
        self.assertIn(app.id, Menu.with_user(self.employee)._visible_menu_ids())
        self.assertIn(app.id, profile.om_tree_state()['granted_apps'])
        report = self.env['om.access.test.user'].with_user(self.manager).create({'user_id': self.employee.id}).report
        self.assertIn('OM Buying / User', report)
        # the profile archived, the access goes with it
        profile.active = False
        self.env.invalidate_all()
        self.assertNotIn(user_group, self.employee.all_group_ids)
        profile.active = True
        self.env.invalidate_all()
        self.assertIn(user_group, self.employee.all_group_ids)
        # and back to the user's own groups
        profile.om_menu_panel_set(app.id, {'kind': 'grant', 'privilege_id': privilege.id, 'group_id': False})
        self.env.invalidate_all()
        self.assertNotIn(user_group, self.employee.all_group_ids)
        self.assertNotIn(app.id, Menu.with_user(self.employee)._visible_menu_ids())

    def test_administrators_are_never_granted(self):
        from odoo.exceptions import ValidationError
        profile = self.env['om.access.profile'].with_user(self.manager).create({'name': 'Greedy'})
        for xmlid in ('base.group_system', 'base.group_erp_manager', 'om_access_manager.group_access_manager'):
            with self.assertRaises(ValidationError):
                profile.granted_group_ids = self.env.ref(xmlid)
        sneaky = self.env['res.groups'].create({
            'name': 'Sneaky', 'implied_ids': [(4, self.env.ref('base.group_erp_manager').id)]})
        with self.assertRaises(ValidationError):
            profile.granted_group_ids = sneaky
