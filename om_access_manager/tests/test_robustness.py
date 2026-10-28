# What must hold whatever the setup: tabs and Settings apps in any language,
# link buttons as well as buttons, and nothing granted left behind by an uninstall.
from lxml import etree

from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.om_access_manager import uninstall_hook


@tagged('post_install', '-at_install')
class TestRobustness(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.user = new_test_user(cls.env, 'om_access_robust_user',
                                 groups='base.group_user,base.group_partner_manager')

    def _profile(self, **values):
        return self.env['om.access.profile'].create(dict(values, name='Robust', user_ids=[(6, 0, self.user.ids)]))

    def _arch(self, model_name='res.partner', view_type='form', view_id=None, user=None):
        Model = self.env[model_name].with_user(user or self.user)
        return etree.fromstring(Model.get_view(view_id, view_type=view_type)['arch'])

    def test_a_tab_rule_holds_in_every_language(self):
        self.env['res.lang']._activate_lang('fr_FR')
        page = self._arch(user=self.env.ref('base.user_admin')).xpath('//page[@name]')[0].get('name')
        self._profile(element_ids=[(0, 0, {'model_id': self.partner_model.id, 'element_type': 'page',
                                           'element_name': page, 'element_label': 'In English'})])
        for lang in ('en_US', 'fr_FR'):
            self.user.lang = lang
            self.assertFalse(self._arch().xpath(f"//page[@name='{page}']"), lang)

    def test_link_buttons_are_hidden_scanned_and_offered(self):
        view = self.env['ir.ui.view'].create({
            'name': 'om_access_manager test: a kanban with a link',
            'model': 'res.partner',
            'type': 'kanban',
            'arch': """
                <kanban>
                    <templates><t t-name="card">
                        <field name="name"/>
                        <a type="object" name="action_archive">Archive it</a>
                    </t></templates>
                </kanban>""",
        })
        profile = self._profile(button_ids=[(0, 0, {
            'model_id': self.partner_model.id, 'button_type': 'object', 'button_name': 'action_archive',
            'mode': 'hide'})])
        self.assertTrue(self._arch(view_type='kanban', view_id=view.id, user=self.env.ref('base.user_admin'))
                        .xpath("//a[@name='action_archive']"))
        self.assertFalse(self._arch(view_type='kanban', view_id=view.id).xpath("//a[@name='action_archive']"))
        # the scan and the panel find it, with its text as label
        view.priority = 1
        found = {(button['button_name'], button['button_label'])
                 for button in self.env['om.access.scan.buttons']._scan('res.partner')}
        self.assertIn(('action_archive', 'Archive it'), found)
        self.assertFalse(profile._om_health_check().filtered(lambda issue: issue.kind == 'unmatched'))

    def test_the_uninstall_takes_back_what_the_profiles_granted(self):
        granted = self.env['res.groups'].create({'name': 'OM Granted by a Profile'})
        profile = self._profile(granted_group_ids=[(6, 0, granted.ids)])
        technical = profile.group_id
        self.assertIn(granted, self.user.groups_id)
        uninstall_hook(self.env)
        self.assertFalse(technical.exists())
        self.assertNotIn(granted, self.user.groups_id)
        self.assertIn(self.env.ref('base.group_partner_manager'), self.user.groups_id,
                      "the user keeps the groups of their own form")
