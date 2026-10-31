# Your turn: the challenges, done the way a learner does them when the app is
# built live: in Odoo's technical menus, a field added, views edited, a field
# made required, an access right changed.
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner


@tagged('post_install', '-at_install')
class TestChallenges(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()
        self.addCleanup(lambda: self.Progress.search([])._reset())

    def build(self, key):
        self.Progress.academy_set_mode(key, 'live')
        payload = self.Progress.academy_set_level(key, 'basic')
        self.Progress.academy_build(key, len(payload['steps']) - 1)
        return self.Progress._get(key)

    def check(self, course, key):
        return self.Progress.academy_challenge_check(course, key)

    def test_first_app(self):
        progress = self.build('library')
        finish = self.Progress.academy_step('library', len(progress._level_course()['steps']) - 1)
        self.assertEqual([challenge['key'] for challenge in finish['challenges']], ['notes', 'filter', 'required'])
        self.assertIn('Technical', finish['challenges'][0]['hint'], "built live, the hint is about the technical menus")

        self.assertFalse(self.check('library', 'notes')['ok'])
        model = self.env['ir.model']._get('x_library_book')
        self.env['ir.model.fields'].create({'model_id': model.id, 'name': 'x_notes', 'field_description': 'Notes',
                                            'ttype': 'text'})
        self.assertIn('not in the form', self.check('library', 'notes')['message'])
        form = progress._live().record('library_book_view_form')
        form.arch = form.arch.replace('</group>', '<field name="x_notes"/></group>', 1)
        self.assertTrue(self.check('library', 'notes')['ok'])

        self.assertFalse(self.check('library', 'filter')['ok'])
        search = progress._live().record('library_book_view_search')
        search.arch = search.arch.replace('</search>', '<filter name="available" string="Available" '
                                                       'domain="[(\'x_state\', \'=\', \'available\')]"/></search>')
        self.assertTrue(self.check('library', 'filter')['ok'])

        self.assertFalse(self.check('library', 'required')['ok'])
        # as a learner does first: no book left without its author, or Odoo cannot make the column NOT NULL
        author = self.env['x_library_author'].create({'x_name': 'Tolkien'})
        self.env['x_library_book'].search([('x_author_id', '=', False)]).x_author_id = author
        self.env.flush_all()  # in the database before Odoo adds the constraint with SQL
        # Odoo checks the constraint while it reloads, before it adds it: a passing warning, as when a learner does it
        with mute_logger('odoo.schema'):
            progress._live().record('field:library.book.author_id').write({'required': True, 'on_delete': 'restrict'})
        result = self.check('library', 'required')
        self.assertTrue(result['ok'])
        self.assertTrue(result['all_done'])

    def test_security(self):
        progress = self.build('security')
        self.assertFalse(self.check('security', 'delete')['ok'])
        progress._live().record('access_todo_task_user').operation = 'crud'
        self.assertTrue(self.check('security', 'delete')['ok'])

    def test_every_course_has_challenges(self):
        for key, course in COURSES_BY_KEY.items():
            self.assertTrue(course.get('challenges'), key)

    def test_trophies_and_certificate(self):
        home = self.Progress.academy_home()
        self.assertFalse(any(trophy['earned'] for trophy in home['trophies']))
        self.assertEqual(home['shelf'], [])
        self.Progress.academy_set_identity('hotel', {'author_name': 'Test Learner'})
        progress = self.build('hotel')
        self.assertTrue(progress.completed_on)
        home = self.Progress.academy_home()
        self.assertEqual([app['name'] for app in home['shelf']], ['Hotel'])
        earned = {trophy['key'] for trophy in home['trophies'] if trophy['earned']}
        self.assertEqual(earned, {'first_app'})
        certificate = progress._certificate()
        self.assertEqual(certificate['name'], 'Test Learner')
        self.assertEqual(certificate['app'], 'Hotel')
        self.assertIn('A model to store rooms', certificate['learned'])
        action = self.Progress.academy_certificate('hotel')
        self.assertEqual(action['type'], 'ir.actions.report')
        for what in ('report', 'template'):
            opened = self.Progress.academy_certificate_behind(what)
            self.assertEqual(opened['res_model'], 'ir.actions.report' if what == 'report' else 'ir.ui.view')
        html = self.env['ir.actions.report']._render_qweb_html('om_academy.action_report_certificate', progress.ids)[0]
        self.assertIn(b'Test Learner', html)
        self.assertIn(b'Certificate of Completion', html)

    def test_the_last_step_follows_the_others(self):
        self.Progress.academy_set_mode('car_rental', 'live')
        payload = self.Progress.academy_set_level('car_rental', 'basic')
        keys = [step['key'] for step in payload['steps']]
        self.Progress.academy_build('car_rental', keys.index('compute'))
        progress = self.Progress._get('car_rental')
        self.assertNotIn('finish', progress.built, "never built itself")
        self.assertIn('finish', progress._done_keys())
        self.assertTrue(progress.completed_on, "the app is complete: certificate, trophies")
        home = {course['key']: course for course in self.Progress.academy_home()['courses']}
        self.assertEqual(home['car_rental']['done'], home['car_rental']['steps'])

    def test_certificate_of_all_courses(self):
        with self.assertRaisesRegex(UserError, 'Complete a course first'):
            self.Progress.academy_certificate_all()
        for key in ('hotel', 'kanban'):
            self.Progress.academy_set_identity(key, {'author_name': 'Test Learner'})
            self.build(key)
        action = self.Progress.academy_certificate_all()
        self.assertEqual(action['type'], 'ir.actions.report')
        progresses = self.Progress.search([('completed_on', '!=', False)])
        certificate = progresses._certificate_all()
        self.assertEqual(certificate['count'], 2)
        self.assertEqual([app['name'] for app in certificate['apps']], ['Hotel', 'Ideas'])
        html = self.env['ir.actions.report']._render_qweb_html('om_academy.action_report_certificate_all', progresses.ids)[0]
        self.assertIn(b'Certificate of Achievement', html)
        self.assertEqual(html.count(b'Test Learner'), 1, "one page, for all the courses")

    def test_certificate_names_the_learner_only(self):
        progress = self.Progress._get('hotel')
        progress.write({'author_name': 'Jane Doe, Odoo Mates', 'coauthor': True})
        self.assertEqual(progress._certificate()['name'], 'Jane Doe')
