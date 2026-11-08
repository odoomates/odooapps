# Code it: the files written for the learner stay in their module, and the
# check says what is missing in words a learner understands.
import os
import tempfile
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.models.code_checker import CodeChecker
from odoo.addons.om_academy.models.course_files import files_at
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner

COURSE = COURSES_BY_KEY['library']


@tagged('post_install', '-at_install')
class TestCode(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Progress = self.env['academy.progress']
        # a learner of this database may have built the course live already
        self.Progress.search([])._reset()
        self.Progress.academy_set_mode('library', 'code')
        folder = self.folder = tempfile.mkdtemp()
        patcher = patch.object(type(self.Progress), '_addons_paths', lambda _self: [folder])
        patcher.start()
        self.addCleanup(patcher.stop)
        modules_on_disk(self, folder)
        named_learner(self)
        # the learner picks the folder: none is taken on its own
        for course_key in ('library', 'contacts', 'security'):
            self.Progress.academy_set_path(course_key, folder)

    def test_write_it_for_me(self):
        course = self.Progress._get('library')._level_course()
        index = len(course['steps']) - 1
        result = self.Progress.academy_write('library', index)
        self.assertEqual(result['path'], os.path.join(self.folder, 'learn_library'))
        for path, content in files_at(course, index).items():
            with open(os.path.join(self.folder, 'learn_library', path), 'rb') as handle:
                self.assertEqual(handle.read(), content.encode() if isinstance(content, str) else content)

    def test_no_folder_is_taken_unasked(self):
        progress = self.Progress._get('library')
        progress.addons_path = False
        with patch('odoo.addons.om_academy.models.academy_progress.config') as config:
            config.addons_data_dir = '/nowhere'
            self.assertFalse(progress._module_path(), "a repository of modules is never picked on its own")
            with self.assertRaises(UserError):
                self.Progress.academy_write('library', 1)

    def test_a_folder_must_be_an_addons_path(self):
        with self.assertRaises(UserError):
            self.Progress.academy_set_path('library', '/tmp/elsewhere')
        self.Progress.academy_set_path('library', self.folder)
        self.assertEqual(self.Progress._get('library').addons_path, self.folder)

    def test_the_check_before_the_module_exists(self):
        result = self.Progress.academy_check('library', 2)
        self.assertFalse(result['passed'])
        [failure] = result['results']
        self.assertIn('learn_library', failure['text'])
        self.assertTrue(failure['hint'])

    def test_the_check_reads_the_registry(self):
        # a model of Odoo checked as if the course asked for it: what the check says
        course = dict(COURSE, module='base')
        checker = CodeChecker(self.env, course)
        checker._check_model('res.partner', {
            'fields': {
                'name': {'type': 'char'},
                'type': {'type': 'char'},
                'nothing_here': {'type': 'char'},
            },
            'methods': {'action_archive': {}, 'action_dance': {}},
        })
        texts = [(result['ok'], result['text']) for result in checker.results]
        self.assertIn((True, 'The field res.partner.name is right.'), texts)
        self.assertIn((False, 'The field res.partner.type is a Selection: it should be a Char.'), texts)
        self.assertIn((False, 'The field res.partner.nothing_here is missing.'), texts)
        self.assertIn((True, 'The method res.partner.action_archive() exists.'), texts)
        self.assertIn((False, 'The method res.partner.action_dance() is missing.'), texts)

    def test_restart_odoo(self):
        from odoo.addons.om_academy.models import academy_progress
        restarted = []
        with patch.object(academy_progress.server, 'restart', lambda: restarted.append(True)), \
                patch.object(academy_progress, 'dev_mode', lambda: []):
            with self.assertRaisesRegex(UserError, 'developer mode'):
                self.Progress.academy_restart()
            self.assertFalse(self.Progress.academy_open('library')['can_restart'])
        with patch.object(academy_progress.server, 'restart', lambda: restarted.append(True)), \
                patch.object(academy_progress, 'dev_mode', lambda: ['xml']):
            self.assertTrue(self.Progress.academy_open('library')['can_restart'])
            self.Progress.academy_restart()
            self.assertFalse(restarted, "not before the answer is sent")
            self.env.cr.postcommit.run()
            self.assertEqual(restarted, [True])
        steps = {step['key']: step['index'] for step in self.Progress.academy_open('library')['steps']}
        self.assertTrue(self.Progress.academy_step('library', steps['model'])['python_changed'])
        self.assertFalse(self.Progress.academy_step('library', steps['form'])['python_changed'])
