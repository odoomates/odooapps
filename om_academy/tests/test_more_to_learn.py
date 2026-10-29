# What there is to learn besides the courses: the bug hunt, the videos, the
# interview round, the streak; and the course of Owl, written in the editor.
import os
import tempfile
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES, COURSES_BY_KEY
from odoo.addons.om_academy.courses.videos import STEP_VIDEOS, VIDEOS_BY_ID
from odoo.addons.om_academy.models.bugs import BUGS
from odoo.addons.om_academy.models.code_checker import CodeChecker
from odoo.addons.om_academy.models.warmup import QUESTIONS
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner


@tagged('post_install', '-at_install')
class TestMoreToLearn(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Progress = self.env['academy.progress']
        self.Bugs = self.env['academy.bugs']
        self.env.user.write({'academy_bugs': False, 'academy_days': False, 'academy_warmup': False})
        self.Progress.search([('user_id', '=', self.env.uid)]).unlink()

    def test_the_bug_hunt(self):
        data = self.Bugs.academy_bugs()
        self.assertEqual(len(data['bugs']), len(BUGS))
        self.assertFalse(any(bug['answer'] for bug in data['bugs']), "no answer shown before it is found")
        bug = BUGS[0]
        wrong = (bug['right'] + 1) % len(bug['options'])
        result = self.Bugs.academy_bug_answer(bug['key'], wrong)
        self.assertFalse(result['correct'])
        self.assertNotIn('why', result, "a wrong answer gives a hint, not the answer")
        result = self.Bugs.academy_bug_answer(bug['key'], bug['right'])
        self.assertTrue(result['correct'])
        self.assertEqual(result['fix'], bug['fix'])
        data = self.Bugs.academy_bugs()
        self.assertEqual(data['found'], 1)
        self.assertEqual(data['bugs'][0]['tries'], 1)
        self.assertTrue(data['bugs'][0]['answer'], "a bug found keeps its answer")
        with self.assertRaises(UserError):
            self.Bugs.academy_bug_answer('no_such_bug', 0)
        # all of them found: a trophy
        for bug in BUGS:
            result = self.Bugs.academy_bug_answer(bug['key'], bug['right'])
        self.assertTrue(result['all_found'])
        trophies = {trophy['key']: trophy for trophy in self.Progress.academy_home()['trophies']}
        self.assertTrue(trophies['bug_hunter']['earned'])

    def test_every_bug_has_four_reasons(self):
        for bug in BUGS:
            with self.subTest(bug=bug['key']):
                self.assertEqual(len(bug['options']), 4)
                self.assertIn(bug['right'], range(4))
                self.assertTrue(bug['code'] and bug['error'] and bug['fix'] and bug['why'] and bug['hint'])

    def test_the_streak(self):
        user = self.env.user
        today = fields.Date.context_today(user)
        self.assertEqual(user._academy_streak(), {'current': 0, 'best': 0, 'today': False})
        user.academy_days = [fields.Date.to_string(today - timedelta(days=n)) for n in (6, 5, 2, 1)]
        self.assertEqual(user._academy_streak(), {'current': 2, 'best': 2, 'today': False})
        # a question answered: today counts
        self.Bugs.academy_bug_answer(BUGS[0]['key'], 0)
        self.assertEqual(user._academy_streak(), {'current': 3, 'best': 3, 'today': True})
        self.assertEqual(self.Progress.academy_home()['streak']['current'], 3)
        # a day missed: the streak starts again
        user.academy_days = [fields.Date.to_string(today - timedelta(days=n)) for n in (4, 3)]
        self.assertEqual(user._academy_streak()['current'], 0)

    def test_the_videos(self):
        home = self.Progress.academy_home()
        self.assertEqual(len(home['videos']), len(VIDEOS_BY_ID))
        self.assertTrue(home['playlist_url'].startswith('https://www.youtube.com/playlist?list='))
        self.assertTrue(all(video['url'].startswith('https://www.youtube.com/watch?v=') for video in home['videos']))
        for (_course, _step), ids in STEP_VIDEOS.items():
            self.assertLessEqual(set(ids), set(VIDEOS_BY_ID))
        step_keys = {(course.get('family') or course['key'], step['key']) for course in COURSES
                     for step in course['steps']} | {(course['key'], step['key']) for course in COURSES
                                                     for step in course['steps']}
        self.assertLessEqual(set(STEP_VIDEOS), step_keys, "a video is linked to a step that does not exist")
        named_learner(self)
        course = self.Progress.academy_open('library')
        index = next(step['index'] for step in course['steps'] if step['key'] == 'compute')
        videos = self.Progress.academy_step('library', index)['videos']
        self.assertEqual([video['id'] for video in videos], ['MmBFfqBevLI'])

    def test_the_interview_round(self):
        questions = [question for question in QUESTIONS if question['topic'] == 'interview']
        self.assertGreaterEqual(len(questions), 8)
        data = self.env['academy.warmup'].academy_warmup_start('interview')
        self.assertTrue(all(question['key'].startswith('i_') for question in data['round']['questions']))

    def test_the_app_in_numbers(self):
        named_learner(self)
        course = self.Progress.academy_open('library')
        finish = self.Progress.academy_step('library', len(course['steps']) - 1)
        numbers = finish['numbers']
        self.assertGreater(numbers['lines'], 50)
        self.assertEqual(numbers['models'], 2)
        self.assertGreaterEqual(numbers['views'], 3)
        self.assertFalse(self.Progress.academy_step('library', 1)['numbers'], "the numbers come at the finish")


@tagged('post_install', '-at_install')
class TestOwlCourse(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Progress = self.env['academy.progress']
        self.Progress.search([('user_id', '=', self.env.uid), ('course_key', '=', 'owl')]).unlink()
        folder = self.folder = tempfile.mkdtemp()
        patcher = patch.object(type(self.Progress), '_addons_paths', lambda _self: [folder])
        patcher.start()
        self.addCleanup(patcher.stop)
        modules_on_disk(self, folder)
        for target in ('odoo.addons.om_academy.models.code_checker.get_module_path',
                       'odoo.addons.om_academy.models.challenges.get_module_path'):
            patcher = patch(target, lambda name, **kwargs: os.path.join(folder, name)
                            if os.path.isdir(os.path.join(folder, name)) else False)
            patcher.start()
            self.addCleanup(patcher.stop)
        named_learner(self)

    def test_written_in_the_editor_only(self):
        course = self.Progress.academy_open('owl')
        self.assertEqual(course['mode'], 'code')
        self.assertEqual(course['modes'], ['code'])
        with self.assertRaises(UserError):
            self.Progress.academy_set_mode('owl', 'live')
        self.assertEqual(self.Progress.academy_open('library')['modes'], ['live', 'code'])

    def test_the_files_are_checked(self):
        self.Progress.academy_set_path('owl', self.folder)
        course = COURSES_BY_KEY['owl']
        index = next(index for index, step in enumerate(course['steps']) if step['key'] == 'state')
        checker = CodeChecker(self.env, course)
        # nothing written yet
        checker.results = []
        checker._check_files(course['steps'][index]['checks'][0])
        self.assertFalse(checker.results[0]['ok'])
        # the step before: the file lacks what this step adds
        self.Progress.academy_write('owl', index - 1)
        checker.results = []
        checker._check_files(course['steps'][index]['checks'][0])
        self.assertFalse(checker.results[0]['ok'])
        self.assertIn('proxy(', checker.results[0]['text'])
        # written: right, and the manifest loads the assets
        self.Progress.academy_write('owl', index)
        checker.results = []
        for extra in course['steps'][index]['checks']:
            getattr(checker, '_check_' + extra['kind'])(extra)
        self.assertTrue(all(result['ok'] for result in checker.results), checker.results)
        checker.results = []
        checker._check_assets({'kind': 'assets', 'bundle': 'web.assets_backend'})
        self.assertTrue(checker.results[0]['ok'], checker.results)

    def test_the_challenges_read_the_code(self):
        self.Progress.academy_set_path('owl', self.folder)
        course = COURSES_BY_KEY['owl']
        self.Progress.academy_write('owl', len(course['steps']) - 1)
        result = self.Progress.academy_challenge_check('owl', 'reset')
        self.assertFalse(result['ok'])
        root = os.path.join(self.folder, 'learn_owl')
        with open(os.path.join(root, 'static/src/lab/lab.js'), 'a', encoding='utf-8') as handle:
            handle.write("\nclass More { reset() { this.state.count = 0; } }\n")
        with open(os.path.join(root, 'static/src/lab/lab.xml'), 'r+', encoding='utf-8') as handle:
            content = handle.read().replace('</templates>', '<button t-on-click="() => this.reset()"/></templates>')
            handle.seek(0)
            handle.write(content)
        self.assertTrue(self.Progress.academy_challenge_check('owl', 'reset')['ok'])
