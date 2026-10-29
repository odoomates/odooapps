# Basic, or Basic + a little more: the extra steps (conditions, a chatter,
# tracking) built live and working, and taken back when going back to Basic.
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.courses import COURSES_BY_KEY
from odoo.addons.om_academy.tests.common import modules_on_disk, named_learner

COURSE = COURSES_BY_KEY['library']
EXTRA = [step['key'] for step in COURSE['steps'] if step.get('level') == 'more']


@tagged('post_install', '-at_install')
class TestLevels(TransactionCase):

    def setUp(self):
        super().setUp()
        modules_on_disk(self)
        named_learner(self)
        self.Progress = self.env['academy.progress']
        self.Progress.search([])._reset()
        self.Progress.academy_set_mode('library', 'live')

    def keys(self, payload):
        return [step['key'] for step in payload['steps']]

    def test_basic_leaves_the_extra_steps_out(self):
        payload = self.Progress.academy_set_level('library', 'basic')
        self.assertFalse(set(EXTRA) & set(self.keys(payload)))
        basic, more = payload['levels']
        self.assertEqual(basic['extra'], [])
        self.assertEqual(len(more["extra"]), 3)
        self.assertEqual(basic['steps'], more['steps'], "the same base, and the difference marked apart")

    def test_more_builds_a_chatter_and_tracking(self):
        if not self.env['ir.module.module'].search_count([('name', '=', 'mail'), ('state', '=', 'installed')]):
            self.skipTest("Discuss is not installed in this database")
        payload = self.Progress.academy_set_level('library', 'more')
        keys = self.keys(payload)
        self.assertEqual(keys[-4:], EXTRA + ['finish'])
        self.Progress.academy_build('library', len(keys) - 1)

        model = self.env['ir.model']._get('x_library_book')
        self.assertTrue(model.is_mail_thread)
        form = self.env['x_library_book'].get_view(view_type='form')['arch']
        self.assertIn('<chatter', form)
        self.assertIn("readonly=\"x_state == 'borrowed'\"", form)
        self.assertIn("required=\"x_state == 'borrowed'\"", form)

        # Odoo writes the tracking when the transaction commits, and does not
        # track a record created in the same transaction
        book = self.env['x_library_book'].create({'x_name': 'Dune'})
        self.env.cr.precommit.run()
        book.x_state = 'borrowed'
        self.env.cr.precommit.run()
        self.assertTrue(book.message_ids.filtered(lambda message: message.message_type == 'tracking'),
                        "the status change is in the chatter")

        # back to Basic: the extra steps are undone, the chatter leaves the form
        payload = self.Progress.academy_set_level('library', 'basic')
        self.assertFalse(set(EXTRA) & set(self.Progress._get('library').built))
        form = self.env['x_library_book'].get_view(view_type='form')['arch']
        self.assertNotIn('<chatter', form)
        self.assertNotIn('readonly="x_state', form)
        field = self.env['ir.model.fields']._get('x_library_book', 'x_state')
        self.assertFalse(field.tracking)
