# The warm-up: the quiz answered, and the tasks done by hand in Odoo, each
# checked in the database.
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.om_academy.models.warmup import QUESTIONS, ROUND_SIZE


@tagged('post_install', '-at_install')
class TestWarmup(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Warmup = self.env['academy.warmup']
        self.env.user.academy_warmup = False
        self.env['academy.progress'].search([('user_id', '=', self.env.uid)]).unlink()

    def right_option(self, question):
        """ The right option of a question of the round, as it is shown. """
        asked = next(item for item in QUESTIONS if item['key'] == question['key'])
        return question['options'].index(str(asked['options'][asked['right']]))

    def play(self, topic, right=True):
        """ A round of the topic, answered right (or wrong): the questions asked, the result. """
        questions = self.Warmup.academy_warmup_start(topic)['round']['questions']
        result = None
        for question in questions:
            choice = self.right_option(question)
            if not right:
                choice = (choice + 1) % len(question['options'])
            result = self.Warmup.academy_warmup_answer(question['key'], choice)['result']
        return [question['key'] for question in questions], result

    def test_a_round(self):
        data = self.Warmup.academy_warmup_start('odoo')
        round_ = data['round']
        self.assertEqual(len(round_['questions']), ROUND_SIZE)
        self.assertNotIn('right', round_['questions'][0], "the answers are not sent with the questions")
        first = round_['questions'][0]
        right = self.right_option(first)
        answer = self.Warmup.academy_warmup_answer(first['key'], right)
        self.assertTrue(answer['correct'])
        self.assertEqual(answer['right'], right, "the right option, as it is shown")
        self.assertFalse(answer['result'], "the round goes on")
        with self.assertRaises(UserError):
            self.Warmup.academy_warmup_answer('not_asked', 0)

    def test_rounds_are_kept_and_differ(self):
        first, result = self.play('odoo')
        self.assertEqual(result, {'score': ROUND_SIZE, 'total': ROUND_SIZE, 'record': False})
        second, result = self.play('odoo', right=False)
        self.assertEqual(result['score'], 0)
        # the questions seen the least come first: a second round asks others
        pool = [question['key'] for question in QUESTIONS if question['topic'] == 'odoo']
        self.assertEqual(len(set(first) & set(second)), max(0, 2 * ROUND_SIZE - len(pool)))
        data = self.Warmup.academy_warmup()
        self.assertEqual([(round_['score'], round_['total']) for round_ in data['history']],
                         [(0, ROUND_SIZE), (ROUND_SIZE, ROUND_SIZE)], "the last round first")
        odoo = next(topic for topic in data['topics'] if topic['key'] == 'odoo')
        self.assertEqual(odoo['best'], [ROUND_SIZE, ROUND_SIZE])
        self.assertEqual(data['right'], ROUND_SIZE)

    def test_what_you_built_follows_the_steps_done(self):
        topic = lambda: next(topic for topic in self.Warmup.academy_warmup()['topics'] if topic['key'] == 'built')
        self.assertEqual(topic()['count'], 0, "nothing built: nothing to ask")
        with self.assertRaises(UserError):
            self.Warmup.academy_warmup_start('built')
        progress = self.env['academy.progress']._get('library')
        progress.write({'mode': 'live', 'built': ['skeleton', 'model']})
        keys = {question['key'] for question in self.Warmup.academy_warmup_start('built')['round']['questions']}
        expected = {question['key'] for question in QUESTIONS
                    if question['needs'] and question['needs'][1] in ('skeleton', 'model')
                    and question['needs'][0] == 'first_app'}
        self.assertEqual(keys, expected)

    def test_the_quiz_of_before(self):
        # right answers of the quiz before rounds count still
        self.env.user.academy_warmup = {'start': '2026-01-01 00:00:00', 'apps': [], 'tasks': {},
                                        'answers': {'country': {'choice': 1, 'correct': True}}}
        self.assertEqual(self.Warmup.academy_warmup()['right'], 1)

    def test_the_tasks_are_checked(self):
        # whatever the database holds already is not the learner's doing
        self.env['res.partner'].search([('name', '=ilike', 'odoo mates')]).name = 'Somebody else'
        self.env['res.users'].search([('name', 'ilike', 'niyas')]).name = 'Somebody else'
        self.Warmup.academy_warmup()
        check = self.Warmup.academy_warmup_check
        self.assertFalse(check('customer')['ok'])
        partner = self.env['res.partner'].create({'name': 'Odoo Mates'})
        self.assertIn('email', check('customer')['message'])
        partner.email = 'odoomates@gmail.com'
        self.assertTrue(check('customer')['ok'])

        self.assertFalse(check('user')['ok'])
        self.env['res.users'].create({'name': 'Niyas', 'login': 'om_academy_niyas'})
        self.assertTrue(check('user')['ok'])

        self.assertFalse(check('app', 'om_academy')['ok'], "installed before the warm-up began")
        self.assertFalse(check('technical', 'mail')['ok'])
        self.assertTrue(check('technical', ' Email ')['ok'])

        if 'mail.thread' in self.env.registry:
            self.assertFalse(check('chatter')['ok'])
            partner.message_post(body='Hello from the Academy', message_type='comment')
            result = check('chatter')
            self.assertTrue(result['ok'], result['message'])
            self.assertIn('Odoo Mates', result['message'])
        done = {task['key'] for task in self.Warmup.academy_warmup()['tasks'] if task['done']}
        self.assertLessEqual({'customer', 'user', 'technical'}, done)

    def test_find_it(self):
        find = self.Warmup.academy_warmup_find
        data = self.Warmup.academy_warmup()
        self.assertEqual(len(data['finds']), 6)
        self.assertFalse(find('console', 'wrong')['ok'])
        self.assertTrue(find('console', ' %s ' % data['secret'].upper())['ok'])
        self.assertFalse(find('debug', False)['ok'])
        self.assertTrue(find('debug', True)['ok'])
        self.assertIn('contacts', find('model', 'res.partner')['message'])
        self.assertTrue(find('model', 'res.users')['ok'])
        self.assertFalse(find('record_id', '0')['ok'])
        self.assertTrue(find('record_id', str(self.env.uid))['ok'])
        self.assertTrue(find('xmlid', self.env.company.get_external_id()[self.env.company.id])['ok'])
        self.assertFalse(find('view_id', 'abc')['ok'])
        self.assertFalse(find('view_id', str(self.env.ref('base.view_partner_form').id))['ok'])
        self.assertTrue(find('view_id', str(self.env.ref('base.view_users_form').id))['ok'])
        self.assertTrue(all(item['done'] for item in self.Warmup.academy_warmup()['finds']))
