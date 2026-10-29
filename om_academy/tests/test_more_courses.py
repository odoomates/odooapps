# The courses beyond the first: extending Odoo's contacts, and securing an app
# with groups and domains, built live.
import datetime

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner


def last(course_key):
    return len(COURSES_BY_KEY[course_key]['steps']) - 1


@tagged('post_install', '-at_install')
class TestMoreCourses(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()

    def test_contacts_extends_odoo(self):
        self.Progress.academy_set_mode('contacts', 'live')
        self.Progress.academy_build('contacts', last('contacts'))
        Partner = self.env['res.partner']
        partner = Partner.create({'name': 'Member', 'x_member_level': 'gold',
                                  'x_member_since': datetime.date.today() - datetime.timedelta(days=800)})
        self.assertEqual(partner.x_member_years, 2)
        for view_type in ('form', 'list', 'search'):
            self.assertIn('x_member_level', Partner.get_view(view_type=view_type)['arch'], view_type)
        self.Progress.academy_reset('contacts')
        self.assertNotIn('x_member_level', self.env['res.partner']._fields, "Odoo's model is left as it was")

    def test_security_the_odoo_20_way(self):
        self.Progress.academy_set_mode('security', 'live')
        self.Progress.academy_build('security', last('security'))
        live_map = self.Progress._get('security').live_map
        user_group = self.env['res.groups'].browse(live_map['learn_todo_group_user'][1])
        manager_group = self.env['res.groups'].browse(live_map['learn_todo_group_manager'][1])
        self.assertIn(self.env.ref('base.user_admin'), manager_group.user_ids)
        self.assertIn(user_group, manager_group.implied_ids)
        alice = self.env['res.users'].create({
            'name': 'Alice', 'login': 'om_academy_alice',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, user_group.id])],
        })
        Task = self.env['x_todo_task']
        Task.create([{'x_name': 'Mine', 'x_user_id': alice.id}, {'x_name': 'Not mine', 'x_user_id': self.env.uid}])
        self.assertEqual(Task.with_user(alice).search([]).mapped('x_name'), ['Mine'])
        with self.assertRaises(AccessError):
            Task.with_user(alice).search([]).unlink()
        self.assertEqual(len(Task.with_user(self.env.ref('base.user_admin')).search([])), 2)
        # managers only: the menu of the tasks done, and the column of whom a task is for
        menu = self.env['ir.ui.menu'].search([('name', '=', 'Done Tasks')])
        Menu = self.env['ir.ui.menu']
        self.assertNotIn(menu.id, Menu.with_user(alice)._visible_menu_ids())
        self.assertIn(menu.id, Menu.with_user(self.env.ref('base.user_admin'))._visible_menu_ids())
        self.assertNotIn('x_user_id', Task.with_user(alice).get_view(view_type='list')['arch'])
        self.assertIn('x_user_id', Task.with_user(self.env.ref('base.user_admin')).get_view(view_type='list')['arch'])
        done = self.env['ir.actions.act_window'].search([('name', '=', 'Done Tasks')])
        self.assertEqual(done.domain, "[('x_is_done', '=', True)]")
        # the line of the access rights the CSV file dropped comes back on undo
        while self.Progress._get('security').built[-1] != 'groups':
            self.Progress.academy_undo('security')
        accesses = self.env['ir.access'].search([('model_id.model', '=', 'x_todo_task')])
        self.assertEqual(accesses.mapped('operation'), ['crud'])
        self.assertEqual(accesses.group_id, self.env.ref('base.group_user'))

    def test_kanban_board(self):
        self.Progress.academy_set_mode('kanban', 'live')
        self.Progress.academy_build('kanban', last('kanban'))
        Stage = self.env['x_idea_stage']
        self.assertEqual(Stage.search([]).mapped('x_name'), ['New', 'In Progress', 'Done'], "the data file, in order")
        self.assertTrue(Stage.search([('x_name', '=', 'Done')]).x_fold)
        Card = self.env['x_idea_card']
        card = Card.create({'x_name': 'An idea', 'x_stage_id': Stage.search([], limit=1).id})
        self.assertEqual(card.x_priority, '0', "the default of the selection")
        arch = Card.get_view(view_type='kanban')['arch']
        self.assertIn('default_group_by="x_stage_id"', arch)
        # as the board asks: every column, empty ones included
        groups = Card.with_context(read_group_expand=True).web_read_group([], ['x_stage_id'], [])['groups']
        self.assertEqual(len(groups), 3, "every stage is a column, even the empty ones")
        self.Progress.academy_reset('kanban')
        self.assertNotIn('x_idea_card', self.env.registry)

    def test_report_prints(self):
        self.Progress.academy_set_mode('report', 'live')
        self.Progress.academy_build('report', last('report'))
        live = self.Progress._get('report')._live()
        report = live.record('action_report_contact_card')
        self.assertEqual(report.binding_model_id.model, 'res.partner', "in the Print menu of the contacts")
        self.assertEqual(report.paperformat_id.format, 'A5')
        company = self.env['res.partner'].create({'name': 'Odoo Mates', 'is_company': True, 'website': 'https://odoomates.tech'})
        self.env['res.partner'].create({'name': 'Niyas', 'parent_id': company.id, 'email': 'niyas@example.com'})
        html = self.env['ir.actions.report']._render_qweb_html(report, company.ids)[0]
        for text in (b'Odoo Mates', b'odoomates.tech', b'niyas@example.com'):
            self.assertIn(text, html)
        self.assertFalse(self.Progress.academy_challenge_check('report', 'second')['ok'])
        self.Progress.academy_reset('report')
        self.assertFalse(report.exists())
        self.assertFalse(self.env['ir.ui.view'].search([('key', '=', 'om_academy_live.report_contact_card')]))
