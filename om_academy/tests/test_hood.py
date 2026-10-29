# Under the hood: what each step made, read from PostgreSQL.
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner


@tagged('post_install', '-at_install')
class TestHood(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()
        self.addCleanup(lambda: self.Progress.search([])._reset())
        self.Progress.academy_set_mode('library', 'live')
        self.Progress.academy_set_level('library', 'basic')
        self.index = {step['key']: step['index'] for step in self.Progress.academy_open('library')['steps']}

    def hood(self, key):
        return self.Progress.academy_hood('library', self.index[key])

    def table(self, hood, name):
        return next(table for table in hood['tables'] if table['table'] == name)

    def test_the_table_of_a_model(self):
        before = self.table(self.hood('model'), 'x_library_book')
        self.assertFalse(before['exists'], "not built yet")
        self.assertIn('CREATE TABLE x_library_book', before['sql'])
        self.Progress.academy_build('library', self.index['model'])
        table = self.table(self.hood('model'), 'x_library_book')
        self.assertTrue(table['exists'])
        self.assertEqual([column['name'] for column in table['columns']], ['id', 'x_name', 'x_author', 'x_date_published'])
        self.assertEqual(table['count'], 0)
        self.env['x_library_book'].create({'x_name': 'Dune'})
        table = self.table(self.hood('model'), 'x_library_book')
        self.assertEqual(table['count'], 1)
        self.assertIn('Dune', table['rows'][0])

    def test_a_link_and_a_computed_field(self):
        self.Progress.academy_build('library', self.index['compute'])
        authors = self.hood('authors')
        book = self.table(authors, 'x_library_book')
        link = next(column for column in book['columns'] if column['name'] == 'x_author_id')
        self.assertEqual(link['link'], 'x_library_author.id')
        self.assertTrue(link['new'])
        self.assertIn('ALTER TABLE x_library_book ADD COLUMN x_author_id INT4 REFERENCES x_library_author', book['sql'])
        self.assertIn('x_library_author', [table['table'] for table in authors['tables']])
        compute = self.table(self.hood('compute'), 'x_library_book')
        days = next(column for column in compute['columns'] if column['name'] == 'x_days_borrowed')
        self.assertFalse(days['stored'])
        self.assertFalse(days['exists'], "a computed field is no column")
        self.assertIn('x_days_borrowed: no column', compute['sql'])

    def test_records_of_odoo_tables(self):
        self.Progress.academy_build('library', self.index['access'])
        tables = {records['table']: records for records in self.hood('access')['records']}
        self.assertEqual(tables['ir_access']['rows'][0][2], 'crud')
        tables = {records['table']: records for records in self.hood('skeleton')['records']}
        self.assertEqual(tables['ir_module_module']['rows'][0][0], 'learn_library')

    def test_every_step_of_every_course(self):
        from odoo.addons.om_academy.courses import COURSES
        for course in COURSES:
            self.Progress.academy_set_mode(course['key'], 'live')
            for step in self.Progress.academy_open(course['key'])['steps']:
                with self.subTest(course=course['key'], step=step['key']):
                    self.Progress.academy_hood(course['key'], step['index'])
