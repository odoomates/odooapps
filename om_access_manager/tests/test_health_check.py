# The Health Check: what the database removed under a profile, what its rules
# no longer match, the filters that no longer evaluate, and the records gone.
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from .audit import HttpCase


@tagged('post_install', '-at_install')
class TestHealthCheck(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.menu = cls.env['ir.ui.menu'].create({'name': 'OM Health Menu'})
        cls.env['ir.model.data'].create({
            'module': 'om_access_manager', 'name': 'om_health_test_menu',
            'model': 'ir.ui.menu', 'res_id': cls.menu.id,
        })
        cls.profile = cls.env['om.access.profile'].create({
            'name': 'Healthy',
            'hidden_menu_ids': [(6, 0, cls.menu.ids)],
            'model_ids': [(0, 0, {'model_id': cls.partner_model.id, 'domain': "[('name', '!=', 'Secret')]"})],
            'button_ids': [(0, 0, {'model_id': cls.partner_model.id, 'button_type': 'object',
                                   'button_name': 'action_archive', 'mode': 'block'})],
            'element_ids': [(0, 0, {'model_id': cls.partner_model.id, 'element_type': 'filter',
                                    'element_name': 'inactive'})],
        })

    def setUp(self):
        super().setUp()
        # versions are saved when the transaction commits; the one queued while
        # the class was set up may not reach this test
        self.env.cr.precommit.run()
        self.env['om.access.profile']._om_version_missing()

    def _issues(self, kind=None):
        issues = self.profile._om_health_check()
        return issues.filtered(lambda issue: issue.kind == kind) if kind else issues

    def test_all_good(self):
        self.assertFalse(self._issues())
        action = self.profile.action_health_check()
        self.assertEqual(action['params']['title'], "All good")

    def test_a_rule_lost_with_its_menu(self):
        self.env.cr.execute("DELETE FROM ir_ui_menu WHERE id = %s", [self.menu.id])
        self.env['base'].invalidate_cache()
        [issue] = self._issues('lost')
        self.assertEqual(issue.name, 'OM Health Menu')
        self.assertFalse(issue.restorable)
        self.assertIn('Health Check', self.profile.message_ids[0].body)
        # a second run says nothing new in the chatter
        messages = len(self.profile.message_ids)
        self._issues()
        self.assertEqual(len(self.profile.message_ids), messages)
        # accepting it saves the profile as it is
        self.profile.health_issue_ids.action_remove()
        self.env.cr.precommit.run()
        self.assertFalse(self._issues())

    def test_a_menu_back_brings_its_rule_back(self):
        self.env.cr.execute("DELETE FROM ir_ui_menu WHERE id = %s", [self.menu.id])
        self.env['base'].invalidate_cache()
        menu = self.env['ir.ui.menu'].create({'name': 'OM Health Menu'})
        self.env['ir.model.data'].search([('name', '=', 'om_health_test_menu')]).res_id = menu.id
        # Odoo 18 looks up external ids in the database without flushing first
        self.env['base'].flush()
        self.env.registry.clear_caches()
        [issue] = self._issues('lost')
        self.assertTrue(issue.restorable)
        issue.action_restore()
        self.assertEqual(self.profile.hidden_menu_ids, menu)
        self.assertFalse(self.profile.health_issue_ids)

    def test_rules_matching_nothing(self):
        self.env['om.access.profile.button'].create({
            'profile_id': self.profile.id, 'model_id': self.partner_model.id, 'button_type': 'object',
            'button_name': 'om_no_such_method', 'mode': 'block'})
        self.env['om.access.profile.element'].create({
            'profile_id': self.profile.id, 'model_id': self.partner_model.id, 'element_type': 'page',
            'element_name': 'om_no_such_page'})
        self.env.cr.precommit.run()
        issues = self._issues('unmatched')
        self.assertEqual(len(issues), 2)
        page = issues.filtered(lambda issue: issue.res_model == 'om.access.profile.element')
        page.action_remove()
        self.assertNotIn('om_no_such_page', self.profile.element_ids.mapped('element_name'))

    def test_a_filter_that_no_longer_evaluates(self):
        line = self.profile.model_ids
        self.env.cr.execute("UPDATE om_access_profile_model SET domain = %s WHERE id = %s",
                            ["[('om_gone_field', '=', 1)]", line.id])
        self.env['base'].invalidate_cache()
        [issue] = self._issues('broken')
        self.assertEqual((issue.res_model, issue.res_id), (line._name, line.id))
        self.assertIn('om_gone_field', issue.details)

    def test_an_action_button_whose_action_is_gone(self):
        action = self.env['ir.actions.act_window'].create({'name': 'Gone Soon', 'res_model': 'res.partner'})
        self.env['om.access.profile.button'].create({
            'profile_id': self.profile.id, 'model_id': self.partner_model.id, 'button_type': 'action',
            'button_name': str(action.id), 'mode': 'block'})
        self.env.cr.precommit.run()
        action.unlink()
        self.assertTrue(self._issues('missing'))

    def test_every_week_and_only_for_access_managers(self):
        cron = self.env.ref('om_access_manager.ir_cron_health_check')
        self.assertEqual((cron.interval_number, cron.interval_type), (1, 'weeks'))
        self.env.cr.execute("DELETE FROM ir_ui_menu WHERE id = %s", [self.menu.id])
        self.env['base'].invalidate_cache()
        self.env['om.access.profile']._cron_health_check()
        self.assertTrue(self.profile.health_issue_ids)
        user = new_test_user(self.env, 'om_access_health_user', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['om.access.health.issue'].with_user(user).search([])
        menu = self.env.ref('om_access_manager.om_access_health_menu')
        self.assertNotIn(menu.id, self.env['ir.ui.menu'].with_user(user)._visible_menu_ids())


@tagged('post_install', '-at_install')
class TestHealthCheckScreen(HttpCase):

    def test_the_menu_lists_and_fixes(self):
        profile = self.env['om.access.profile'].create({
            'name': 'Needs a Look',
            'element_ids': [(0, 0, {'model_id': self.env['ir.model']._get('res.partner').id,
                                    'element_type': 'page', 'element_name': 'om_no_such_page'})],
        })
        code = """(async () => {
            const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const until = async (selector) => {
                for (let tries = 0; tries < 75; tries++) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element;
                    }
                    await wait(200);
                }
                throw new Error('not found: ' + selector);
            };
            (await until('.o_group_header')).click();
            const row = await until('.o_data_row');
            if (!row.innerText.includes('om_no_such_page')) {
                throw new Error('the rule is not listed: ' + row.innerText);
            }
            row.querySelector('button[name=action_remove]').click();
            for (let tries = 0; tries < 50 && document.querySelector('.o_data_row'); tries++) {
                await wait(200);
            }
            if (document.querySelector('.o_data_row')) {
                throw new Error('the rule is still listed');
            }
            console.log('test successful');
        })()"""
        self.browser_js('/web#action=om_access_manager.om_access_health_check_server_action', code,
                        login='admin', timeout=90)
        self.assertFalse(profile.element_ids)
