# Build your first app, on every subject: the same steps, each app working,
# each its own module in Apps.
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.courses.first_app import THEMES
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner


@tagged('post_install', '-at_install')
class TestSubjects(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()
        self.addCleanup(lambda: self.Progress.search([])._reset())

    def test_every_subject_builds_and_works(self):
        has_mail = bool(self.env['ir.module.module'].search_count([('name', '=', 'mail'), ('state', '=', 'installed')]))
        for theme in THEMES:
            with self.subTest(subject=theme['key']):
                key = theme['key']
                self.Progress.academy_set_mode(key, 'live')
                payload = self.Progress.academy_set_level(key, 'more' if has_mail else 'basic')
                self.assertEqual(payload['name'], 'Build a %s app' % theme['App'])
                self.Progress.academy_build(key, len(payload['steps']) - 1)
                module = self.env['ir.module.module'].search([('name', '=', theme['module'])])
                self.assertEqual(module.shortdesc, theme['App'])
                Item = self.env['x_%s_%s' % (theme['p'], theme['item'])]
                maker = self.env['x_%s_%s' % (theme['p'], theme['maker'])].create({'x_name': 'Maker'})
                item = Item.create({'x_name': 'One', 'x_%s_id' % theme['maker']: maker.id})
                self.assertEqual(item.x_state, 'available')
                take = self.env['ir.actions.server'].search([('name', '=', theme['Take']),
                                                              ('model_id.model', '=', Item._name)])
                take.with_context(active_model=Item._name, active_id=item.id, active_ids=item.ids).run()
                self.assertEqual(item.x_state, theme['taken'])
                self.assertTrue(item['x_' + theme['date2']])
                # the next subject: this one stays, the Academy lets go of it
                self.Progress.academy_reset(key)

    def test_subject_words_everywhere(self):
        course = COURSES_BY_KEY['hotel']
        texts = ' '.join(str(step['title']) + str(step.get('explain', '')) for step in course['steps'])
        self.assertIn('rooms', texts)
        for word in ('book', 'authors', 'borrow', 'Library'):  # 'author' of the manifest stays
            self.assertNotIn(word, texts.replace('Odoo', ''))
