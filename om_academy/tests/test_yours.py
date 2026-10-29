# Make it yours: the learner is the author of their module (Odoo Mates too, if
# they agree), and their app has the icon they pick or upload.
import ast
import base64

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open

from odoo.addons.om_academy.models.course_files import ICON_PATH, files_at
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner


@tagged('post_install', '-at_install')
class TestYours(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()
        self.Progress.academy_set_mode('library', 'live')
        self.Progress.academy_set_level('library', 'basic')

    def manifest(self):
        course = self.Progress._get('library')._level_course()
        return ast.literal_eval(files_at(course, len(course['steps']) - 1)['__manifest__.py'])

    def test_the_learner_is_the_author(self):
        self.Progress.academy_set_identity('library', {'author_name': 'Jane Doe', 'coauthor': False})
        self.assertEqual(self.manifest()['author'], 'Jane Doe')
        payload = self.Progress.academy_set_identity('library', {'coauthor': True})
        self.assertEqual(self.manifest()['author'], 'Jane Doe, Odoo Mates')
        self.assertEqual(payload['author'], 'Jane Doe, Odoo Mates')
        # the next course starts with the same author
        self.assertEqual(self.Progress.academy_open('security')['author'], 'Jane Doe, Odoo Mates')

    def test_the_icon_of_the_app(self):
        self.Progress.academy_set_identity('library', {'icon': 'rocket'})
        course = self.Progress._get('library')._level_course()
        with file_open('om_academy/static/img/icons/rocket.png', 'rb') as handle:
            self.assertEqual(files_at(course, 1)[ICON_PATH], handle.read())
        # built live, the app takes the icon, and another one picked later
        self.Progress.academy_build('library', 4)
        root = self.env['ir.ui.menu'].search([('name', '=', 'Library'), ('parent_id', '=', False)])
        self.assertEqual(root.web_icon, 'om_academy,static/img/icons/rocket.png')
        self.Progress.academy_set_identity('library', {'icon': 'leaf'})
        self.assertEqual(root.web_icon, 'om_academy,static/img/icons/leaf.png')
        # an icon of their own
        with file_open('om_academy/static/img/icons/star.png', 'rb') as handle:
            mine = handle.read()
        payload = self.Progress.academy_set_identity('library', {'icon_data': base64.b64encode(mine).decode()})
        self.assertEqual(payload['icon'], 'custom')
        self.assertEqual(files_at(self.Progress._get('library')._level_course(), 1)[ICON_PATH], mine)
        self.assertFalse(root.web_icon)
        self.assertTrue(root.web_icon_data)

    def test_no_build_before_the_name(self):
        progress = self.Progress._get('library')
        progress.author_name = False
        self.assertEqual(self.Progress.academy_open('library')['author_name'], '')
        with self.assertRaisesRegex(UserError, 'Write your name first'):
            self.Progress.academy_build('library', 1)
        with self.assertRaisesRegex(UserError, 'Write your name first'):
            self.Progress.academy_write('library', 1)
        self.Progress.academy_set_identity('library', {'author_name': 'Jane Doe'})
        self.Progress.academy_build('library', 1)
