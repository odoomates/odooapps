# The finish of a course: the app exported as a module, the live build carried
# on in code, and the learner's files compared with the course's.
import io
import os
import tempfile
import zipfile
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.models.course_files import files_at
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner

COURSE = COURSES_BY_KEY['library']
# the Basic level, the learner's default
INDEX = {step['key']: index for index, step in enumerate(
    step for step in COURSE['steps'] if step.get('level') != 'more')}


@tagged('post_install', '-at_install')
class TestFinish(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()
        folder = self.folder = tempfile.mkdtemp()
        patcher = patch.object(type(self.Progress), '_addons_paths', lambda _self: [folder])
        patcher.start()
        self.addCleanup(patcher.stop)
        modules_on_disk(self, folder)
        named_learner(self)
        # the learner picks the folder: none is taken on its own
        for course_key in ('library', 'contacts', 'security'):
            self.Progress.academy_set_path(course_key, folder)
        self.Progress.academy_set_mode('library', 'live')

    def _zip(self):
        action = self.Progress.academy_export('library')
        attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
        return zipfile.ZipFile(io.BytesIO(bytes(attachment.raw)))

    def test_nothing_to_export_before_a_step(self):
        with self.assertRaises(UserError):
            self.Progress.academy_export('library')

    def test_export_the_steps_built(self):
        self.Progress.academy_build('library', INDEX['menu'])
        names = set(self._zip().namelist())
        self.assertIn('learn_library/__manifest__.py', names)
        self.assertIn('learn_library/views/library_menus.xml', names)
        self.assertIn('learn_library/README.md', names)
        self.assertNotIn('learn_library/views/library_book_views.xml', names, "a step not built yet")

    def test_export_the_whole_app(self):
        self.Progress.academy_build('library', INDEX['finish'])
        archive = self._zip()
        for path, content in files_at(self.Progress._get('library')._level_course(), INDEX['finish']).items():
            self.assertEqual(archive.read('learn_library/' + path),
                             content.encode() if isinstance(content, str) else content)
        book = archive.read('learn_library/models/library_book.py').decode()
        self.assertIn("_name = 'library.book'", book)
        self.assertNotIn('x_', book, "the export speaks module, not live")

    def test_continue_in_code(self):
        self.Progress.academy_build('library', INDEX['form'])
        result = self.Progress.academy_continue('library')
        self.assertEqual(result['course']['mode'], 'code')
        self.assertEqual(result['index'], INDEX['form'])
        with open(os.path.join(self.folder, 'learn_library', 'views', 'library_book_views.xml'), encoding='utf-8') as handle:
            self.assertIn('library_book_view_form', handle.read())

    def test_compare_with_the_reference(self):
        self.Progress.academy_set_mode('library', 'code')
        self.Progress.academy_write('library', INDEX['model'])
        path = os.path.join(self.folder, 'learn_library', 'models', 'library_book.py')
        with open(path, encoding='utf-8') as handle:
            content = handle.read()
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(content.replace("    author = fields.Char()\n", ""))
        os.remove(os.path.join(self.folder, 'learn_library', 'models', '__init__.py'))
        result = {item['path']: item for item in self.Progress.academy_compare('library', INDEX['model'])}
        self.assertEqual(result['__manifest__.py']['status'], 'same')
        self.assertEqual(result['models/__init__.py']['status'], 'missing')
        book = result['models/library_book.py']
        self.assertEqual(book['status'], 'differs')
        self.assertIn({'kind': '+', 'text': '    author = fields.Char()'}, book['lines'])
