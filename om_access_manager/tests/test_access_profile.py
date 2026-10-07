# Every check here is driven with .with_user(): env.su bypasses every hook this
# module installs, so a test written with sudo() would prove nothing.
from unittest.mock import patch

from lxml import etree

from odoo.exceptions import AccessDenied, AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .audit import has_access, modifier


@tagged('post_install', '-at_install')
class TestAccessProfile(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        # A plain internal user lacks create and delete on res.partner with only
        # base installed: grant all four so assertions do not pass by accident.
        cls.category_model = cls.env['ir.model']._get('res.partner.category')
        cls.test_group = cls.env['res.groups'].create({'name': 'OM Access Test Group'})
        cls.env['ir.model.access'].create([
            {
                'name': 'om_access_manager test: partners',
                'model_id': cls.partner_model.id,
                'group_id': cls.test_group.id,
                'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': True,
            },
            {
                # a second model, to check that a rule stays on its own model
                'name': 'om_access_manager test: partner categories',
                'model_id': cls.category_model.id,
                'group_id': cls.test_group.id,
                'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': True,
            },
        ])
        cls.password = 'om-access-manager-test-pw'
        cls.user = cls.env['res.users'].create({
            'name': 'Profiled User',
            'login': 'om_access_profiled',
            'password': cls.password,
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id, cls.test_group.id])],
        })
        cls.Profile = cls.env['om.access.profile']

    def _profile(self, **values):
        values.setdefault('name', 'Test Profile')
        values.setdefault('user_ids', [(6, 0, self.user.ids)])
        return self.Profile.create(values)

    def _rules(self):
        return self.Profile.with_user(self.user)._current_rules()

    def _partner(self):
        return self.env['res.partner'].with_user(self.user)

    def test_profile_creates_and_syncs_its_group(self):
        profile = self._profile()
        self.assertTrue(profile.group_id, "the technical group is created with the profile")
        self.assertIn(self.user, profile.group_id.users)

        other = self.env['res.users'].create({
            'name': 'Other', 'login': 'om_access_other',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        profile.user_ids = [(4, other.id)]
        self.assertIn(other, profile.group_id.users)

        group = profile.group_id
        profile.unlink()
        self.assertFalse(group.exists(), "the group goes with the profile")

    def test_no_profile_means_no_restriction(self):
        self.assertFalse(self._rules().enabled)
        for operation in ('read', 'write', 'create', 'unlink'):
            self.assertTrue(has_access(self._partner().browse(), operation), operation)

    def test_superuser_and_admin_are_exempt(self):
        self._profile(global_readonly=True, apply_to_admin=True, user_ids=[
            (6, 0, [self.env.ref('base.user_admin').id, self.env.ref('base.user_root').id]),
        ])
        for xmlid in ('base.user_admin', 'base.user_root'):
            user = self.env.ref(xmlid)
            self.assertFalse(
                self.Profile._resolve(user.id).enabled,
                "%s must never be restricted" % xmlid)

    def test_settings_users_are_exempt_unless_asked(self):
        self.user.groups_id = [(4, self.env.ref('base.group_system').id)]
        profile = self._profile(global_readonly=True)
        self.assertFalse(self._rules().enabled)
        profile.apply_to_admin = True
        self.assertTrue(self._rules().enabled)

    def test_model_rule_denies_create_and_unlink(self):
        self._profile(model_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'perm_create': False,
            'perm_unlink': False,
        })])
        partners = self._partner()
        self.assertTrue(has_access(partners.browse(), 'read'))
        self.assertTrue(has_access(partners.browse(), 'write'))
        self.assertFalse(has_access(partners.browse(), 'create'))
        self.assertFalse(has_access(partners.browse(), 'unlink'))
        with self.assertRaises(AccessError):
            partners.create({'name': 'Refused'})

    def test_global_readonly(self):
        self._profile(global_readonly=True)
        partners = self._partner()
        self.assertTrue(has_access(partners.browse(), 'read'))
        for operation in ('write', 'create', 'unlink'):
            self.assertFalse(has_access(partners.browse(), operation), operation)

    def test_denied_create_removes_the_button_from_the_view(self):
        self._profile(model_ids=[(0, 0, {
            'model_id': self.partner_model.id, 'perm_create': False,
        })])
        arch = etree.fromstring(self._partner().fields_view_get(view_type='tree')['arch'])
        self.assertEqual(arch.get('create'), 'false',
                         "core derives the Create button from has_access()")

    def test_record_filter(self):
        kept = self.env['res.partner'].create({'name': 'Kept', 'ref': 'keep'})
        hidden = self.env['res.partner'].create({'name': 'Hidden', 'ref': 'drop'})
        self._profile(model_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'domain': "[('ref', '=', 'keep')]",
        })])
        visible = self._partner().search([('id', 'in', (kept + hidden).ids)])
        self.assertEqual(visible, kept.with_user(self.user))

    def test_invalid_record_filter_is_refused(self):
        with self.assertRaises(ValidationError):
            self._profile(model_ids=[(0, 0, {
                'model_id': self.partner_model.id,
                'domain': "[('no_such_field', '=', 1)]",
            })])

    def test_additive_profiles_combine_permissively(self):
        self._profile(name='Strict', model_ids=[(0, 0, {
            'model_id': self.partner_model.id, 'perm_unlink': False,
        })])
        self.assertFalse(has_access(self._partner().browse(), 'unlink'))
        # a second additive profile that says nothing about partners gives the
        # right back, which is what a permissive union means
        self._profile(name='Quiet')
        self.assertTrue(has_access(self._partner().browse(), 'unlink'))

    def test_an_override_profile_always_wins(self):
        self._profile(name='Permissive')
        self._profile(name='Blanket', strictness='override', global_readonly=True)
        partners = self._partner()
        self.assertTrue(has_access(partners.browse(), 'read'))
        self.assertFalse(has_access(partners.browse(), 'write'))

    def test_hidden_menus_include_their_children(self):
        root = self.env['ir.ui.menu'].create({'name': 'Root Menu'})
        child = self.env['ir.ui.menu'].create({'name': 'Child Menu', 'parent_id': root.id})
        self._profile(hidden_menu_ids=[(6, 0, root.ids)])
        blacklist = self.env['ir.ui.menu'].with_user(self.user)._load_menus_blacklist()
        self.assertIn(root.id, blacklist)
        self.assertIn(child.id, blacklist, "a hidden menu hides its children")

    def test_hide_settings_menu(self):
        self._profile(hide_settings_menu=True)
        blacklist = self.env['ir.ui.menu'].with_user(self.user)._load_menus_blacklist()
        self.assertIn(self.env.ref('base.menu_administration').id, blacklist)

    def test_button_is_blocked_on_the_server(self):
        self._profile(button_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'button_type': 'object',
            'button_name': 'action_archive',
            'mode': 'hide_block',
        })])
        Profile = self.Profile.with_user(self.user)
        with self.assertRaises(AccessError):
            Profile._check_button('res.partner', 'object', 'action_archive')
        # a button of another model is untouched
        Profile._check_button('res.users', 'object', 'action_archive')

    def test_button_mode_hide_only_does_not_block(self):
        self._profile(button_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'button_type': 'object',
            'button_name': 'action_archive',
            'mode': 'hide',
        })])
        self.Profile.with_user(self.user)._check_button(
            'res.partner', 'object', 'action_archive')

    def test_action_button_is_blocked_by_its_action_id(self):
        action = self.env['ir.actions.act_window'].create({
            'name': 'Test Action', 'res_model': 'res.partner', 'view_mode': 'tree',
        })
        self._profile(button_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'button_type': 'action',
            'button_name': str(action.id),
            'mode': 'hide_block',
        })])
        # /web/action/load only carries the id, never the view the button was in
        with self.assertRaises(AccessError):
            self.Profile.with_user(self.user)._check_action(action.id)

    def test_hidden_report_is_refused(self):
        report = self.env['ir.actions.report'].search([], limit=1)
        self.assertTrue(report, "the database has at least one report")
        self._profile(hidden_report_ids=[(6, 0, report.ids)])
        with self.assertRaises(AccessError):
            self.Profile.with_user(self.user)._check_action(report.id)

    def test_chatter_is_removed_from_the_form(self):
        self._profile(hide_chatter_all=True)
        arch = self._partner().fields_view_get(view_type='form')['arch']
        self.assertNotIn('<chatter', arch)

    def test_hidden_field_is_hidden_in_nested_views_of_the_same_model(self):
        # res.partner.child_ids is res.partner, so the fields of that nested
        # view carry the rules of res.partner too
        self._profile(field_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'field_id': self.env['ir.model.fields']._get('res.partner', 'phone').id,
            'mode': 'hide',
        })])
        arch = etree.fromstring(self._partner().fields_view_get(view_type='form')['arch'])
        # every phone of the form, the nested contacts' included, is hidden
        phones = arch.xpath("//field[@name='phone']")
        self.assertTrue(phones)
        for node in phones:
            self.assertTrue(modifier(node, 'invisible') is True or modifier(node, 'column_invisible') is True)

    def test_rules_do_not_leak_into_the_view_of_another_model(self):
        self._profile(field_ids=[(0, 0, {
            'model_id': self.env['ir.model']._get('res.users').id,
            'field_id': self.env['ir.model.fields']._get('res.users', 'login').id,
            'mode': 'hide',
        })])
        # 'login' exists on res.users only; a res.partner view must be untouched
        arch = etree.fromstring(self._partner().fields_view_get(view_type='form')['arch'])
        self.assertTrue(arch.xpath("//field[@name='name']"))

    def test_hidden_field_stays_invisible_and_leaves_the_search_view(self):
        # Kept, invisible, where other parts of a view may refer to it; removed
        # where it would be searched. Its value is blanked by the field guard.
        self._profile(field_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'field_id': self.env['ir.model.fields']._get('res.partner', 'phone').id,
            'mode': 'hide',
        })])
        form = etree.fromstring(self._partner().fields_view_get(view_type='form')['arch'])
        node = form.xpath("//form/sheet//field[@name='phone']")[0]
        self.assertEqual((modifier(node, 'invisible'), modifier(node, 'readonly')), (True, True))
        search = etree.fromstring(self._partner().fields_view_get(view_type='search')['arch'])
        self.assertFalse(search.xpath("//field[@name='phone']"))

    def test_readonly_field_stays_but_is_locked(self):
        self._profile(field_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'field_id': self.env['ir.model.fields']._get('res.partner', 'phone').id,
            'mode': 'readonly',
        })])
        arch = etree.fromstring(self._partner().fields_view_get(view_type='form')['arch'])
        nodes = arch.xpath("//field[@name='phone']")
        self.assertTrue(nodes)
        self.assertTrue(all(modifier(node, 'readonly') is True for node in nodes))

    def test_block_archive_makes_active_readonly(self):
        self._profile(block_archive=True)
        described = self._partner().fields_get(allfields=['active'], attributes=['readonly'])
        self.assertTrue(described['active']['readonly'])

    def test_block_archive_refuses_the_write(self):
        partner = self.env['res.partner'].create({'name': 'Archivable'})
        self._profile(block_archive=True)
        with self.assertRaises(UserError):
            partner.with_user(self.user).write({'active': False})
        with self.assertRaises(UserError):
            partner.with_user(self.user).action_archive()
        self.assertTrue(partner.active)

    def test_block_archive_leaves_other_writes_alone(self):
        partner = self.env['res.partner'].create({'name': 'Archivable'})
        self._profile(block_archive=True)
        partner.with_user(self.user).write({'name': 'Renamed'})
        self.assertEqual(partner.name, 'Renamed')

    def test_block_duplicate_refuses_copy(self):
        partner = self.env['res.partner'].create({'name': 'Original'})
        self._profile(model_ids=[(0, 0, {
            'model_id': self.partner_model.id, 'hide_duplicate': True,
        })])
        with self.assertRaises(UserError):
            partner.with_user(self.user).copy()

    def test_model_flags_do_not_reach_another_model(self):
        self._profile(model_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'hide_duplicate': True, 'hide_archive': True,
        })])
        category = self.env['res.partner.category'].create({'name': 'Copyable'})
        self.assertTrue(category.with_user(self.user).copy())
        category.with_user(self.user).write({'active': False})
        self.assertFalse(category.active)

    def test_hidden_report_is_refused_at_every_render_entry_point(self):
        report = self.env['ir.actions.report'].search(
            [('report_type', '=', 'qweb-pdf')], limit=1)
        self.assertTrue(report, "the database has at least one qweb-pdf report")
        self._profile(hidden_report_ids=[(6, 0, report.ids)])
        report = report.with_user(self.user)
        # the report routes reach _render_qweb_pdf without passing through _render
        for method in ('_render', '_render_qweb_pdf', '_render_qweb_html',
                       '_render_qweb_text'):
            with self.assertRaises(AccessError, msg=method):
                getattr(report, method)([1])

    def test_profile_bound_to_a_company_only_applies_to_its_users(self):
        other_company = self.env['res.company'].create({'name': 'Other Company'})
        profile = self._profile(global_readonly=True, company_id=other_company.id)
        self.assertFalse(
            self._rules().enabled,
            "the user does not belong to the company of the profile")
        self.user.write({'company_ids': [(4, other_company.id)]})
        self.assertTrue(self._rules().enabled)
        profile.company_id = False
        self.assertTrue(self._rules().enabled)

    def test_edit_filter_does_not_restrict_reading(self):
        draft = self.env['res.partner'].create({'name': 'Draft', 'ref': 'draft'})
        locked = self.env['res.partner'].create({'name': 'Locked', 'ref': 'locked'})
        self._profile(model_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'domain_write': "[('ref', '=', 'draft')]",
        })])
        partners = self._partner()
        # both stay readable, which is the whole point of a per operation filter
        self.assertEqual(
            partners.search([('id', 'in', (draft + locked).ids)]),
            (draft + locked).with_user(self.user))
        draft.with_user(self.user).write({'name': 'Renamed'})
        with self.assertRaises(AccessError):
            locked.with_user(self.user).write({'name': 'Refused'})

    def test_general_filter_and_operation_filter_are_combined(self):
        self.env['res.partner'].create({'name': 'A', 'ref': 'keep'})
        keep_draft = self.env['res.partner'].create({'name': 'B', 'ref': 'keep'})
        self._profile(model_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'domain': "[('ref', '=', 'keep')]",
            'domain_unlink': "[('name', '=', 'B')]",
        })])
        partners = self._partner()
        self.assertTrue(has_access(keep_draft.with_user(self.user), 'unlink'))
        other = self.env['res.partner'].create({'name': 'C', 'ref': 'keep'})
        self.assertFalse(has_access(other.with_user(self.user), 'unlink'))
        self.assertTrue(has_access(other.with_user(self.user), 'read'))
        self.assertFalse(partners.search([('ref', '!=', 'keep')]))

    def test_block_import(self):
        self._profile(block_import=True)
        with self.assertRaises(UserError):
            self._partner().load(['name'], [['Imported']])
        arch = etree.fromstring(self._partner().fields_view_get(view_type='tree')['arch'])
        self.assertEqual(arch.get('import'), '0')

    def test_hide_notebook_tab(self):
        arch = etree.fromstring(self._partner().fields_view_get(view_type='form')['arch'])
        pages = [node.get('name') for node in arch.xpath('//page') if node.get('name')]
        self.assertTrue(pages, "the partner form has named tabs")
        self._profile(element_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'element_type': 'page',
            'element_name': pages[0],
        })])
        arch = etree.fromstring(self._partner().fields_view_get(view_type='form')['arch'])
        self.assertNotIn(
            pages[0], [node.get('name') for node in arch.xpath('//page')])

    def test_hide_search_filter(self):
        arch = etree.fromstring(self._partner().fields_view_get(view_type='search')['arch'])
        names = [node.get('name') for node in arch.xpath('//filter') if node.get('name')]
        self.assertTrue(names, "the partner search view has named filters")
        self._profile(element_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'element_type': 'filter',
            'element_name': names[0],
        })])
        arch = etree.fromstring(self._partner().fields_view_get(view_type='search')['arch'])
        self.assertNotIn(
            names[0], [node.get('name') for node in arch.xpath('//filter')])

    def test_field_required_and_options(self):
        phone = self.env['ir.model.fields']._get('res.partner', 'phone').id
        parent = self.env['ir.model.fields']._get('res.partner', 'parent_id').id
        self._profile(field_ids=[
            (0, 0, {'model_id': self.partner_model.id, 'field_id': phone,
                    'mode': 'required'}),
            (0, 0, {'model_id': self.partner_model.id, 'field_id': parent,
                    'mode': 'keep', 'no_open': True, 'no_create': True}),
        ])
        arch = etree.fromstring(self._partner().fields_view_get(view_type='form')['arch'])
        for node in arch.xpath("//field[@name='phone']"):
            self.assertIs(modifier(node, 'required'), True)
        nodes = arch.xpath("//field[@name='parent_id']")
        self.assertTrue(nodes)
        for node in nodes:
            self.assertIn('"no_open": true', node.get('options') or '')
            self.assertIn('"no_create": true', node.get('options') or '')

    def test_hidden_view_types_leave_the_action(self):
        self._profile(element_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'element_type': 'view',
            'element_name': 'kanban',
        })])
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'views': [[False, 'tree'], [False, 'kanban'], [False, 'form']],
            'view_mode': 'tree,kanban,form',
        }
        result = self.Profile.with_user(self.user)._filter_action_views(dict(action))
        self.assertEqual([view[1] for view in result['views']], ['tree', 'form'])
        self.assertEqual(result['view_mode'], 'tree,form')

    def test_the_last_view_type_of_an_action_is_never_dropped(self):
        self._profile(element_ids=[(0, 0, {
            'model_id': self.partner_model.id,
            'element_type': 'view',
            'element_name': 'tree',
        })])
        action = {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'views': [[False, 'tree']],
            'view_mode': 'tree',
        }
        result = self.Profile.with_user(self.user)._filter_action_views(dict(action))
        self.assertEqual([view[1] for view in result['views']], ['tree'])

    def test_scan_wizard_finds_and_applies_view_elements(self):
        profile = self._profile()
        wizard = self.env['om.access.scan.buttons'].create({
            'profile_id': profile.id,
            'model_id': self.partner_model.id,
            'target': 'elements',
        })
        wizard.action_scan()
        self.assertEqual(wizard.state, 'select')
        kinds = set(wizard.line_ids.mapped('element_type'))
        self.assertTrue({'page', 'filter'} & kinds,
                        "the partner views have tabs and filters")
        pages = wizard.line_ids.filtered(lambda line: line.element_type == 'page')
        pages[:1].selected = True
        wizard.action_apply()
        self.assertEqual(profile.element_ids.element_type, 'page')
        self.assertEqual(profile.element_ids.element_name, pages[:1].element_name)

    def test_view_element_rule_needs_a_name(self):
        with self.assertRaises(ValidationError):
            self._profile(element_ids=[(0, 0, {
                'model_id': self.partner_model.id,
                'element_type': 'page',
            })])

    def test_unknown_view_type_is_refused(self):
        with self.assertRaises(ValidationError):
            self._profile(element_ids=[(0, 0, {
                'model_id': self.partner_model.id,
                'element_type': 'view',
                'element_name': 'not_a_view',
            })])

    def test_block_rpc_refuses_non_interactive_login(self):
        credential = {
            'login': self.user.login, 'password': self.password, 'type': 'password',
        }
        user = self.user.with_user(self.user)
        # the credentials are valid, so an AccessDenied can only come from the
        # flag and not from the password check of super()
        user._check_credentials(credential['password'], {'interactive': False})
        self._profile(block_rpc=True)
        with self.assertRaises(AccessDenied):
            user._check_credentials(credential['password'], {'interactive': False})
        # the browser is left alone
        user._check_credentials(credential['password'], {'interactive': True})

    def test_block_login_refuses_every_sign_in(self):
        credential = {
            'login': self.user.login, 'password': self.password, 'type': 'password',
        }
        user = self.user.with_user(self.user)
        user._check_credentials(credential['password'], {'interactive': True})
        self._profile(block_login=True)
        for interactive in (True, False):
            with self.assertRaises(AccessDenied):
                user._check_credentials(credential['password'], {'interactive': interactive})

    def test_block_login_changes_the_session_token(self):
        token = self.user._compute_session_token('sid')
        profile = self._profile(block_login=True)
        blocked = self.user._compute_session_token('sid')
        self.assertNotEqual(blocked, token)
        # out of the profile, the user is back with the token they had
        profile.user_ids = [(3, self.user.id)]
        self.assertEqual(self.user._compute_session_token('sid'), token)

    def test_block_login_spares_the_last_administrator(self):
        # drop the exemption of the built-in administrator to reach this case
        admins = self.env.ref('base.group_system').users
        Profile = type(self.env['om.access.profile'])
        with patch.object(Profile, '_exempt_user_ids', lambda self: ()):
            with self.assertRaises(ValidationError):
                self._profile(block_login=True, apply_to_admin=True, user_ids=[(6, 0, admins.ids)])
            # one administrator left out is enough
            self._profile(block_login=True, apply_to_admin=True,
                          user_ids=[(6, 0, (admins - admins[:1]).ids)])

    def test_block_export(self):
        self.user.groups_id = [(4, self.env.ref('base.group_allow_export').id)]
        self._profile(block_export=True)
        self.assertFalse(self.user.with_user(self.user).has_group('base.group_allow_export'))
        with self.assertRaises(UserError):
            self._partner().search([], limit=1).export_data(['name'])
