# Build it live: every step of the course created in the database, working,
# undone exactly, and the course started over.
import datetime

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner

COURSE = COURSES_BY_KEY['library']
# the Basic level, the learner's default
INDEX = {step['key']: index for index, step in enumerate(
    step for step in COURSE['steps'] if step.get('level') != 'more')}


@tagged('post_install', '-at_install')
class TestLive(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        # a learner of this database may have built the course live already
        self.Progress.search([])._reset()
        self.Progress.academy_set_mode('library', 'live')

    def build(self, key):
        return self.Progress.academy_build('library', INDEX[key])

    def test_the_whole_course_builds_and_works(self):
        step = self.build('finish')
        self.assertEqual(step['course']['last_built'], 'finish')
        self.assertTrue(all(item['done'] for item in step['course']['steps'] if not item['intro']))
        Book = self.env['x_library_book']
        for view_type in ('form', 'list', 'search'):
            Book.get_view(view_type=view_type)
        menus = self.env['ir.ui.menu'].search([('name', 'in', ('Library', 'Books', 'Authors'))])
        self.assertEqual(sorted(menus.mapped('complete_name')), ['Library', 'Library/Authors', 'Library/Books'])
        self.assertTrue(menus.filtered(lambda menu: not menu.parent_id).web_icon_data)
        author = self.env['x_library_author'].create({'x_name': 'Tolkien'})
        book = Book.create({'x_name': 'The Hobbit', 'x_author_id': author.id})
        self.assertEqual(book.x_state, 'available', "the default status")
        live_map = self.Progress._get('library').live_map
        borrow = self.env['ir.actions.server'].browse(live_map['method:library.book.action_borrow'][1])
        borrow.with_context(active_model=Book._name, active_id=book.id, active_ids=book.ids).run()
        self.assertEqual(book.x_state, 'borrowed')
        self.assertEqual(book.x_date_borrowed, datetime.date.today())
        book.x_date_borrowed = datetime.date.today() - datetime.timedelta(days=3)
        self.assertEqual(book.x_days_borrowed, 3, "the computed field follows its dependencies")
        form = Book.get_view(view_type='form')['arch']
        self.assertIn('type="action"', form, "the buttons call the server actions")
        self.assertNotIn('x_author"', form, "the text field of the author left the views")

    def test_a_step_builds_the_steps_before_it(self):
        self.build('menu')
        built = self.Progress._get('library').built
        self.assertEqual(built, ['skeleton', 'model', 'access', 'menu'])
        self.assertTrue(self.env['ir.access'].search([('model_id.model', '=', 'x_library_book')]))

    def test_undo_removes_exactly_the_last_step(self):
        self.build('authors')
        self.assertIn('x_author_id', self.env['x_library_book']._fields)
        self.assertNotIn('x_author', self.env['x_library_book']._fields)
        course = self.Progress.academy_undo('library')
        self.assertEqual(course['last_built'], 'list_search')
        self.assertNotIn('x_library_author', self.env.registry)
        self.assertIn('x_author', self.env['x_library_book']._fields, "the dropped field is back")
        self.assertIn('x_author"', self.env['x_library_book'].get_view(view_type='form')['arch'])
        self.build('authors')
        self.assertIn('x_author_id', self.env['x_library_book']._fields, "a step undone builds again")

    def test_start_over(self):
        self.build('finish')
        self.Progress.academy_reset('library')
        self.assertNotIn('x_library_book', self.env.registry)
        self.assertFalse(self.env['ir.ui.menu'].search([('name', '=', 'Library')]))
        self.assertFalse(self.Progress._get('library').built)
        with self.assertRaises(UserError):
            self.Progress.academy_undo('library')

    def test_see_it_opens_what_the_step_made(self):
        self.build('compute')
        self.assertEqual(self.Progress.academy_see('library', INDEX['model'])['res_model'], 'ir.model')
        self.assertEqual(self.Progress.academy_see('library', INDEX['menu'])['res_model'], 'x_library_book')
        form = self.Progress.academy_see('library', INDEX['form'])
        self.assertEqual(form['views'], [[False, 'form']])

    def test_the_screen_gets_the_step(self):
        step = self.Progress.academy_step('library', INDEX['model'])
        self.assertEqual(step['files'][0]['path'].split('/')[0], 'learn_library')
        book = next(file for file in step['files'] if file['path'].endswith('library_book.py'))
        self.assertTrue(all(line['new'] for line in book['lines']), "a new file is all new")
        self.assertFalse(step['built'])
        home = self.Progress.academy_home()
        self.assertEqual(home['courses'][0]['key'], 'library')

    def test_one_live_build_per_database(self):
        self.build('model')
        other = self.env['res.users'].create({
            'name': 'Second Learner', 'login': 'om_academy_second',
            'group_ids': [(6, 0, [self.env.ref('base.group_system').id])],
        })
        with self.assertRaisesRegex(UserError, 'already exists in this database'):
            self.Progress.with_user(other).academy_build('library', INDEX['model'])
