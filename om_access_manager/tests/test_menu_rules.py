# Rights set on a menu reach the data of its whole branch: the closest setting
# wins, shared data is left alone unless asked, and data opened from several
# menus takes the most restrictive of their settings.
from unittest.mock import patch

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMenuRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env['res.groups'].create({'name': 'OM Menu Rules Test Group'})
        IrModel = cls.env['ir.model']
        cls.env['ir.access'].create([
            {'name': f'om_access_manager menu rules: {name}', 'model_id': IrModel._get(name).id,
             'group_id': group.id, 'operation': 'crud'}
            for name in ('res.partner', 'res.partner.category', 'res.partner.industry', 'res.country.state')
        ])
        cls.user = cls.env['res.users'].create({
            'name': 'Menu Rules User', 'login': 'om_access_menu_rules',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, group.id])],
        })
        Menu = cls.env['ir.ui.menu']
        cls.shop = Menu.create({'name': 'OM Shop'})
        cls.docs = Menu.create({'name': 'Docs', 'parent_id': cls.shop.id})
        cls.tags = Menu.create({'name': 'Tags', 'parent_id': cls.docs.id,
                                'action': cls._action('res.partner.category')})
        cls.config = Menu.create({'name': 'Configuration', 'parent_id': cls.shop.id})
        cls.industries = Menu.create({'name': 'Industries', 'parent_id': cls.config.id,
                                      'action': cls._action('res.partner.industry')})
        cls.customers = Menu.create({'name': 'Customers', 'parent_id': cls.shop.id,
                                     'action': cls._action('res.partner')})
        # contacts are opened by another app too: shared data
        cls.other = Menu.create({'name': 'OM Other'})
        cls.people = Menu.create({'name': 'People', 'parent_id': cls.other.id,
                                  'action': cls._action('res.partner')})
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Menu Rules', 'user_ids': [(6, 0, cls.user.ids)]})

    @classmethod
    def _action(cls, model_name):
        action = cls.env['ir.actions.act_window'].create({'name': model_name, 'res_model': model_name})
        return f'ir.actions.act_window,{action.id}'

    def _rule(self, menu, **values):
        return self.env['om.access.profile.menu'].create(dict(values, profile_id=self.profile.id, menu_id=menu.id))

    def _allows(self, model_name, operation):
        return self.env['om.access.profile'].with_user(self.user)._current_rules().allows(model_name, operation)

    def test_a_read_only_app_makes_its_data_read_only(self):
        self._rule(self.shop, perm_write=False, perm_create=False, perm_unlink=False)
        for model_name in ('res.partner.category', 'res.partner.industry'):
            self.assertTrue(self._allows(model_name, 'read'))
            self.assertFalse(self._allows(model_name, 'write'), model_name)
            self.assertFalse(self._allows(model_name, 'create'), model_name)
        # enforced by the server
        tag = self.env['res.partner.category'].create({'name': 'Tag'})
        with self.assertRaises(AccessError):
            tag.with_user(self.user).name = 'Renamed'
        # contacts are shared with another app: left alone
        self.assertTrue(self._allows('res.partner', 'write'))

    def test_shared_data_on_request(self):
        self._rule(self.shop, perm_write=False, include_shared=True)
        self.assertFalse(self._allows('res.partner', 'write'))

    def test_the_closest_setting_wins(self):
        self._rule(self.shop, perm_write=False, perm_create=False, perm_unlink=False)
        self._rule(self.config)
        self.assertTrue(self._allows('res.partner.industry', 'write'))
        self.assertFalse(self._allows('res.partner.category', 'write'))
        # a rule on the data itself comes before any menu
        self.env['om.access.profile.model'].create({
            'profile_id': self.profile.id, 'model_id': self.env['ir.model']._get('res.partner.category').id})
        self.assertTrue(self._allows('res.partner.category', 'write'))

    def test_a_menu_added_later_follows_its_parent(self):
        self._rule(self.shop, perm_unlink=False)
        self.assertTrue(self._allows('res.country.state', 'unlink'))
        self.env['ir.ui.menu'].create({'name': 'States', 'parent_id': self.config.id,
                                       'action': self._action('res.country.state')})
        self.assertFalse(self._allows('res.country.state', 'unlink'))

    def test_data_under_two_branches_takes_the_most_restrictive(self):
        self._rule(self.shop, perm_write=False, include_shared=True)
        self._rule(self.other, perm_unlink=False, include_shared=True)
        self.assertFalse(self._allows('res.partner', 'write'))
        self.assertFalse(self._allows('res.partner', 'unlink'))
        self.assertTrue(self._allows('res.partner', 'create'))

    def test_their_own_records_where_the_data_has_an_owner(self):
        self._rule(self.other, records='own', hide_export=True, include_shared=True)
        rules = self.env['om.access.profile'].with_user(self.user)._current_rules()
        or_groups, _and_groups = rules.record_domains('res.partner', 'read')
        self.assertEqual(or_groups, (("[('user_id', '=', uid)]",),))
        self.assertTrue(rules.model_flag('res.partner', 'hide_export'))
        mine = self.env['res.partner'].create({'name': 'Mine', 'user_id': self.user.id})
        theirs = self.env['res.partner'].create({'name': 'Theirs'})
        found = self.env['res.partner'].with_user(self.user).search([('id', 'in', (mine | theirs).ids)])
        self.assertEqual(found, mine)

    def test_export_import_and_copy_carry_the_menu_rules(self):
        self._rule(self.shop, perm_write=False, records='company', edit_draft_only=True)
        imported = self.env['om.access.profile']._om_import(self.profile._om_export())
        self.assertEqual(
            (imported.menu_rule_ids.menu_id, imported.menu_rule_ids.perm_write,
             imported.menu_rule_ids.records, imported.menu_rule_ids.edit_draft_only),
            (self.shop, False, 'company', True))
        target = self.env['om.access.profile'].create({'name': 'Target'})
        self.env['om.access.copy.restrictions'].create({
            'profile_id': target.id, 'source_id': self.profile.id}).action_copy()
        self.assertEqual(target.menu_rule_ids.menu_id, self.shop)

    #
    # the panel of the Menus & Apps tab
    #

    def _panel(self, menu, **change):
        if change:
            return self.profile.om_menu_panel_set(menu.id, change)
        return self.profile.om_menu_panel(menu.id)

    def test_the_panel_of_a_menu_opening_data(self):
        panel = self._panel(self.tags)
        self.assertEqual((panel['model'], panel['source'], panel['rights']['perm_create']),
                         ('res.partner.category', False, True))
        self.assertIn('name', [field['name'] for field in panel['fields']])
        # a box unticked makes a rule on the data; ticked again, the rule goes
        panel = self._panel(self.tags, kind='data_rights', perm_create=False)
        self.assertEqual((panel['source'], panel['rights']['perm_create']), ('data', False))
        self.assertFalse(self._allows('res.partner.category', 'create'))
        self._panel(self.tags, kind='data_rights', perm_create=True)
        self.assertFalse(self.profile.model_ids)

    def test_the_panel_follows_the_menu_above(self):
        self._panel(self.shop, kind='menu_rights', perm_write=False)
        panel = self._panel(self.tags)
        self.assertEqual((panel['source'], panel['rights']['perm_write']), ('menu', False))
        self.assertEqual(self._panel(self.docs)['inherited']['menu'], 'OM Shop')
        # changing one box of the data keeps what the menu gave
        self._panel(self.tags, kind='data_rights', perm_unlink=False, hide_export=True)
        line = self.profile.model_ids
        self.assertEqual((line.perm_write, line.perm_unlink, line.hide_export), (False, False, True))
        # back to the menu's settings
        self._panel(self.tags, kind='data_reset')
        self.assertFalse(self.profile.model_ids)
        self._panel(self.shop, kind='menu_reset')
        self.assertTrue(self._allows('res.partner.category', 'write'))

    def test_records_and_drafts_from_the_panel(self):
        panel = self._panel(self.customers)
        self.assertIn('own', [key for key, _label in panel['record_choices']])
        # a box changed on the data keeps the records the menu above gives
        self._panel(self.other, kind='menu_rights', records='own', include_shared=True)
        panel = self._panel(self.customers, kind='data_rights', perm_unlink=False)
        self.assertEqual((panel['source'], panel['rights']['records']), ('data', 'own'))
        self.profile.model_ids.unlink()
        self.profile.menu_rule_ids.unlink()
        panel = self._panel(self.customers, kind='data_rights', records='own')
        self.assertEqual(panel['rights']['records'], 'own')
        self.assertEqual(self.profile.model_ids.domain, "[('user_id', '=', uid)]")

    def test_access_levels(self):
        self._panel(self.shop, kind='level', level='user')
        self.assertEqual(self.profile.hidden_menu_ids, self.config)
        self._panel(self.shop, kind='level', level='readonly')
        self.assertFalse(self.profile.hidden_menu_ids)
        self.assertFalse(self._allows('res.partner.category', 'write'))
        self._panel(self.shop, kind='level', level='none')
        self.assertEqual(self.profile.hidden_menu_ids, self.shop)
        self.assertFalse(self._allows('res.partner.category', 'read'))
        self._panel(self.shop, kind='level', level='full')
        self.assertFalse(self.profile.hidden_menu_ids)
        self.assertFalse(self.profile.menu_rule_ids)

    def test_fields_buttons_tabs_and_prints_from_the_panel(self):
        self._panel(self.customers, kind='field', field='email', mode='hide')
        self._panel(self.customers, kind='field', field='phone', mode='readonly', condition="is_company")
        self._panel(self.customers, kind='button', button_type='object', button_name='action_archive',
                    label='Archive', mode='hide_block')
        self._panel(self.customers, kind='element', element_type='view', element_name='kanban', hidden=True)
        report = self.env['ir.actions.report'].create({
            'name': 'Partner Sheet', 'model': 'res.partner', 'report_name': 'base.partner_sheet'})
        panel = self._panel(self.customers, kind='print', type='ir.actions.report', id=report.id, hidden=True)
        fields = {field['name']: field for field in panel['fields']}
        self.assertEqual((fields['email']['mode'], fields['phone']['mode'], fields['phone']['condition']),
                         ('hide', 'readonly', 'is_company'))
        self.assertIn(('action_archive', 'hide_block'),
                      [(button['button_name'], button['mode']) for button in panel['buttons']])
        self.assertIn(('view', 'kanban', True), [
            (element['element_type'], element['element_name'], element['hidden']) for element in panel['elements']])
        self.assertIn((report.id, True), [(entry['id'], entry['hidden']) for entry in panel['print']])
        state = self.profile.om_tree_state()['models']['res.partner']
        self.assertEqual((state['fields'], state['buttons'], state['elements'], state['print']), (2, 1, 1, 1))
        # back to visible: the lines go
        self._panel(self.customers, kind='field', field='email', mode='keep')
        self._panel(self.customers, kind='button', button_type='object', button_name='action_archive', mode='visible')
        self.assertEqual(self.profile.field_ids.field_id.name, 'phone')
        self.assertFalse(self.profile.button_ids)

    def test_the_tree_tells_the_data_and_the_shared_ones(self):
        menus = {menu['id']: menu for menu in self.env['om.access.profile'].om_menu_tree()}
        self.assertEqual((menus[self.tags.id]['model'], menus[self.tags.id]['shared']),
                         ('res.partner.category', False))
        self.assertTrue(menus[self.customers.id]['shared'])
        with self.assertRaises(AccessError):
            self.env['om.access.profile'].with_user(self.user).om_menu_tree()

    def test_the_panel_says_the_current_level(self):
        self.assertEqual(self._panel(self.shop)['level'], 'full')
        self.assertEqual(self._panel(self.shop, kind='level', level='user')['level'], 'user')
        self.assertEqual(self._panel(self.shop, kind='level', level='readonly')['level'], 'readonly')
        self.assertEqual(self._panel(self.shop, kind='level', level='none')['level'], 'none')
        self.assertEqual(self._panel(self.shop, kind='level', level='full')['level'], 'full')
        self._panel(self.shop, kind='menu_rights', perm_unlink=False)
        self.assertFalse(self._panel(self.shop)['level'])

    def test_effective_access_says_where_a_right_comes_from(self):
        self._rule(self.shop, perm_write=False)
        report = self.env['om.access.test.user'].create({'user_id': self.user.id}).report
        self.assertIn('Menu Rules, from OM Shop', report)

    def test_the_last_administrator_all_profiles_combined(self):
        """ Rules that, all combined, lock every access manager out of the
        access profiles or of the app: refused. """
        Profile = type(self.env['om.access.profile'])
        admins = self.env.ref('om_access_manager.group_access_manager').all_user_ids
        settings = self.env.ref('om_access_manager.om_access_root_menu')
        with patch.object(Profile, '_exempt_user_ids', lambda self: ()):
            reader = self.env['om.access.profile'].create({
                'name': 'Reader', 'apply_to_admin': True, 'user_ids': [(6, 0, admins.ids)]})
            with self.assertRaises(ValidationError):
                self.env['om.access.profile.model'].create({
                    'profile_id': reader.id, 'model_id': self.env['ir.model']._get('om.access.profile').id,
                    'perm_write': False})
            with self.assertRaises(ValidationError):
                reader.hidden_menu_ids = settings
            # one administrator left out is enough
            kept = admins.filtered('active')[:1]
            reader.user_ids = [(3, kept.id)]
            reader.hidden_menu_ids = settings
            # but archiving them is refused
            with self.assertRaises(ValidationError):
                kept.active = False

    def test_a_filter_reading_the_user_follows_the_user(self):
        self.env['om.access.profile.model'].create({
            'profile_id': self.profile.id, 'model_id': self.env['ir.model']._get('res.partner').id,
            'domain': "[('tz', '=', user.tz)]"})
        dubai = self.env['res.partner'].create({'name': 'In Dubai', 'tz': 'Asia/Dubai'})
        paris = self.env['res.partner'].create({'name': 'In Paris', 'tz': 'Europe/Paris'})
        Partner = self.env['res.partner'].with_user(self.user)
        self.user.tz = 'Asia/Dubai'
        self.assertEqual(Partner.search([('id', 'in', (dubai | paris).ids)]), dubai)
        self.user.tz = 'Europe/Paris'
        self.assertEqual(Partner.search([('id', 'in', (dubai | paris).ids)]), paris)

    def test_the_record_choice_skips_the_configuration(self):
        """ "Their own" on an app leaves its reference data (under Configuration)
        whole: only the rights reach it. """
        self.env['ir.ui.menu'].create({'name': 'Salespeople', 'parent_id': self.config.id,
                                       'action': self._action('res.partner')})
        shop_only = self.env['ir.ui.menu'].create({'name': 'Shop Only'})
        self.config.parent_id = shop_only
        self.industries.parent_id = self.config
        self._rule(shop_only, records='own', perm_unlink=False, include_shared=True)
        rules = self.env['om.access.profile'].with_user(self.user)._current_rules()
        # contacts have an owner, and are reached under Shop Only only through
        # its configuration: the rights apply, the record choice does not
        self.assertFalse(rules.allows('res.partner', 'unlink'))
        self.assertEqual(rules.record_domains('res.partner', 'read'), (None, ()))
        # opened from a menu of the app itself, they get the choice
        self.env['ir.ui.menu'].create({'name': 'Clients', 'parent_id': shop_only.id,
                                       'action': self._action('res.partner')})
        rules = self.env['om.access.profile'].with_user(self.user)._current_rules()
        self.assertEqual(rules.record_domains('res.partner', 'read')[0], (("[('user_id', '=', uid)]",),))

    def test_reports_and_actions_on_the_tree(self):
        report = self.env['ir.actions.report'].create({
            'name': 'Tag Sheet', 'model': 'res.partner.category', 'report_name': 'base.tag_sheet'})
        action = self.env['ir.actions.server'].create({
            'name': 'Recolor Tags', 'model_id': self.env['ir.model']._get('res.partner.category').id,
            'binding_model_id': self.env['ir.model']._get('res.partner.category').id, 'state': 'code', 'code': ''})
        prints = self.env['om.access.profile'].om_tree_prints()['res.partner.category']
        self.assertEqual([(entry['label'], entry['kind']) for entry in prints if entry['id'] in (report.id, action.id)],
                         [('Tag Sheet', 'report'), ('Recolor Tags', 'action')])
        self.profile.om_toggle_print('ir.actions.report', report.id, True)
        self.profile.om_toggle_print('ir.actions.server', action.id, True)
        self.assertEqual((self.profile.hidden_report_ids, self.profile.hidden_action_ids), (report, action))
        self.assertEqual(set(self.profile.om_tree_state()['hidden_prints']),
                         {f'ir.actions.report,{report.id}', f'ir.actions.server,{action.id}'})
        rules = self.env['om.access.profile'].with_user(self.user)._current_rules()
        self.assertTrue(rules.hides_report(report.id))
        self.profile.om_toggle_print('ir.actions.report', report.id, False)
        self.assertFalse(self.profile.hidden_report_ids)
