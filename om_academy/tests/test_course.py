# The courses themselves: at every step, the learner's module is valid Python,
# XML and CSV, and the Python part of Build it live matches the Python files.
import ast

from lxml import etree

from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES
from odoo.addons.om_academy.models.course_files import (
    changed_lines, csv_accesses, files_at, manifest_data, models_at, xml_records,
)


@tagged('post_install', '-at_install')
class TestCourses(TransactionCase):

    def test_every_step_leaves_a_valid_module(self):
        for course in COURSES:
            for index, step in enumerate(course['steps']):
                files = files_at(course, index)
                with self.subTest(course=course['key'], step=step['key']):
                    for path, content in files.items():
                        if path.endswith('.py'):
                            compile(content, path, 'exec')
                        elif path.endswith('.xml'):
                            etree.fromstring(content.encode())
                    if '__manifest__.py' in files:
                        manifest = ast.literal_eval(files['__manifest__.py'])
                        self.assertIn('base', manifest['depends'])
                        self.assertLessEqual(set(manifest['depends']), {'base', 'mail', 'web'})
                        for path in manifest_data(files):
                            self.assertIn(path, files, "the manifest loads a file the module lacks")
                    csv_accesses(files)
                    xml_records(files)

    def test_the_live_models_are_those_of_the_python_files(self):
        for course in COURSES:
            for index, step in enumerate(course['steps']):
                files = files_at(course, index)
                python = '\n'.join(content for path, content in files.items() if path.startswith('models/'))
                for model, spec in models_at(course, index).items():
                    with self.subTest(course=course['key'], step=step['key'], model=model):
                        declared = "_inherit = '%s'" if spec.get('existing') else "_name = '%s'"
                        self.assertIn(declared % model, python)
                        for name, field in spec['fields'].items():
                            self.assertIn('%s = fields.%s(' % (name, field['type'].capitalize()), python)
                        for name in spec['methods']:
                            self.assertIn('def %s(self)' % name, python)

    def test_new_lines_are_marked(self):
        course = COURSES[0]
        index = next(i for i, step in enumerate(course['steps']) if step['key'] == 'authors')
        new = changed_lines(course, index, 'models/library_book.py')
        lines = course['steps'][index]['files']['models/library_book.py'].splitlines()
        self.assertEqual([lines[n] for n in sorted(new)],
                         ["    author_id = fields.Many2one('library.author', string='Author')"])

    def test_lines_are_explained(self):
        from odoo.addons.om_academy.models.line_notes import line_note
        for line in ("    _name = 'library.book'", "    author_id = fields.Many2one('library.author', string='Author')",
                     "    @api.depends('date_borrowed', 'state')", '    <record id="x" model="ir.ui.view">',
                     '            <xpath expr="//field[@name=\'category_id\']" position="after">',
                     "access_x,x,x,base.group_user,crud,", "    'depends': ['base'],"):
            self.assertTrue(line_note(line), line)
        # most lines of the first course have a note
        course = COURSES[0]
        files = files_at(course, len(course['steps']) - 1)
        lines = [line for content in files.values() if isinstance(content, str)
                 for line in content.splitlines() if line.strip()]
        explained = [line for line in lines if line_note(line)]
        self.assertGreater(len(explained) / len(lines), 0.7, [line for line in lines if not line_note(line)][:20])
