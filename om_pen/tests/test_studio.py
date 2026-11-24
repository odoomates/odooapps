from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStudio(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, om_pen_studio=True))
        cls.studio = cls.env['om.pen.studio']
        cls.partner_form = cls.env.ref('base.view_partner_form')

    def open_partner(self):
        info = self.studio.studio_open('res.partner', 'form', self.partner_form.id)
        return info['customization_id'], self.studio.studio_view(info['customization_id'])

    def node(self, payload, tag, **attrs):
        for key, node in payload['nodes'].items():
            if node['tag'] == tag and all(node['attrs'].get(name) == value for name, value in attrs.items()):
                return int(key)
        raise AssertionError("no %s %s on the view" % (tag, attrs))

    def live_arch(self):
        self.env.invalidate_all()
        self.env.transaction.invalidate_ormcache('templates')
        return self.env['res.partner'].get_view(self.partner_form.id, 'form')['arch']

    def test_a_change_stays_a_draft_until_published(self):
        cid, view = self.open_partner()
        view = self.studio.studio_change(cid, view['revision'], {
            'op': 'attrs', 'node': self.node(view, 'field', name='function'), 'values': {'string': "Role On Site"}})
        self.assertIn("Role On Site", view['arch'], "the canvas shows the draft")
        self.assertNotIn("Role On Site", self.live_arch(), "nobody else sees it yet")
        self.studio.studio_publish(cid)
        self.assertIn("Role On Site", self.live_arch())
        self.assertEqual(len(self.env['om.pen.view'].browse(cid).version_ids), 1, "publishing keeps a version")

    def test_undo_and_redo(self):
        cid, view = self.open_partner()
        before = view['arch'].count('name="function"')
        view = self.studio.studio_change(cid, view['revision'], {
            'op': 'remove', 'node': self.node(view, 'field', name='function')})
        self.assertEqual(view['arch'].count('name="function"'), before - 1)
        view = self.studio.studio_undo(cid)
        self.assertEqual(view['arch'].count('name="function"'), before)
        self.assertTrue(view['can_redo'])
        view = self.studio.studio_redo(cid)
        self.assertEqual(view['arch'].count('name="function"'), before - 1)

    def test_an_app_is_built_with_its_features(self):
        result = self.studio.studio_new_app({'app_name': "Fleet", 'model_label': "Vehicle",
                                             'features': ['stages', 'tags', 'lines', 'amount', 'dates', 'archiving']})
        Model = self.env[result['model']]
        record = Model.create({'x_name': "Van"})
        self.assertTrue(record.x_stage_id)
        self.assertTrue(record.x_active)
        for view_type in ('form', 'list', 'kanban', 'search', 'calendar'):
            self.assertTrue(Model.get_view(view_type=view_type)['arch'])
        menus = self.studio.studio_menus(result['menu_id'])
        self.assertEqual([child['name'] for child in menus['children']], ["Vehicle", "Configuration"])

    def test_a_button_waits_for_its_approval(self):
        manager = self.env.ref('base.group_system')
        self.studio.studio_approval_save('res.partner', {
            'button_name': 'action_archive', 'button_type': 'object', 'group_id': manager.id})
        partner = self.env['res.partner'].create({'name': "Approve me"})
        Rule = self.env['om.pen.approval.rule']
        self.assertTrue(Rule._blocked_action('res.partner', 'action_archive', partner.ids, 'object'))
        status = Rule.approval_status('res.partner', partner.id, 'action_archive', 'object')
        user = self.env['res.users'].create({'name': "Clerk", 'login': 'clerk_pen'})
        with self.assertRaises(UserError):
            Rule.with_user(user).approval_decide(status['rules'][0]['id'], partner.id, True)
        Rule.approval_decide(status['rules'][0]['id'], partner.id, True)
        self.assertFalse(Rule._blocked_action('res.partner', 'action_archive', partner.ids, 'object'))
