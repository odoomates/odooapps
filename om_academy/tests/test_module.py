# The app built live is a module of the database, as Odoo imports them: in
# Apps, installed, with the learner's name and icon, and owning all it built,
# so that uninstalling it from Apps takes it all away.
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner

COURSE = COURSES_BY_KEY['library']
INDEX = {step['key']: index for index, step in enumerate(
    step for step in COURSE['steps'] if step.get('level') != 'more')}


@tagged('post_install', '-at_install')
class TestModule(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()
        self.Progress.academy_set_mode('library', 'live')
        self.Progress.academy_set_level('library', 'basic')
        self.Progress.academy_set_identity('library', {'author_name': 'Jane Doe', 'coauthor': True, 'icon': 'leaf'})

    def module(self):
        return self.env['ir.module.module'].search([('name', '=', 'learn_library')])

    def test_the_first_step_makes_a_module(self):
        self.Progress.academy_build('library', INDEX['skeleton'])
        module = self.module()
        self.assertRecordValues(module, [{
            'state': 'installed', 'imported': True, 'shortdesc': 'Library', 'application': True,
            'author': 'Jane Doe, Odoo Mates', 'icon': '/learn_library/static/description/icon.png',
        }])
        icon = self.env['ir.attachment'].search([('url', '=', '/learn_library/static/description/icon.png')])
        self.assertTrue(icon.public)
        # the author changes: the module too
        self.Progress.academy_set_identity('library', {'coauthor': False})
        self.assertEqual(module.author, 'Jane Doe')
        # undone, the module goes
        self.Progress.academy_undo('library')
        self.assertFalse(self.module())
        self.assertFalse(icon.exists())

    def test_the_module_owns_the_app_and_takes_it_away(self):
        self.Progress.academy_build('library', INDEX['finish'])
        names = set(self.env['ir.model.data'].search([('module', '=', 'learn_library')]).mapped('name'))
        for name in ('model_x_library_book', 'field_x_library_book__x_name', 'model_x_library_author',
                     'library_book_view_form', 'library_book_action', 'library_root',
                     'access_library_book_user', 'action_server_library_book_action_borrow'):
            self.assertIn(name, names)
        # its Installed Features in Apps
        module = self.module()
        self.assertIn('Library/Books', module.menus_by_module)
        self.assertIn('library.book.view.form (form)', module.views_by_module)
        # uninstalled from Apps: all it built goes, and the Academy starts over
        self.module().module_uninstall()
        self.assertNotIn('x_library_book', self.env.registry)
        self.assertFalse(self.env['ir.ui.menu'].search([('name', '=', 'Library'), ('parent_id', '=', False)]))
        self.assertFalse(self.module())
        payload = self.Progress.academy_open('library')
        self.assertTrue(payload['notice'])
        self.assertFalse(self.Progress._get('library').built)
        # and builds again
        self.Progress.academy_build('library', INDEX['menu'])
        self.assertTrue(self.module())

    def test_start_over_keeping_the_app(self):
        self.Progress.academy_build('library', INDEX['menu'])
        payload = self.Progress.academy_reset('library', keep=True)
        self.assertFalse(any(step['done'] for step in payload['steps']))
        self.assertEqual(self.module().state, 'installed', "the app stays, in Apps")
        self.assertIn('x_library_book', self.env.registry)
        # the same app cannot be built twice: the learner is told to uninstall it first
        with self.assertRaisesRegex(UserError, 'uninstall it from Apps'):
            self.Progress.academy_build('library', INDEX['menu'])
        # what is kept is the learner's: they uninstall it from Apps
        self.module().module_uninstall()
        self.assertNotIn('x_library_book', self.env.registry)

    def test_no_live_build_over_a_module_on_disk(self):
        with patch('odoo.addons.om_academy.models.live_builder.get_module_path', lambda name, **kw: '/addons/' + name):
            with self.assertRaisesRegex(UserError, 'Go on in Code it'):
                self.Progress.academy_build('library', INDEX['skeleton'])
