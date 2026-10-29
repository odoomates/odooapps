# The warm-up, as the Academy screen asks it: the quiz, in rounds, and the tasks
# done by hand in Odoo, checked in the database. What the learner did is kept on
# their user: the round in progress, their scores, the questions seen, the tasks
# done, and what was there when they began.
import random

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..courses import COURSES_BY_KEY
from .warmup import FINDS, QUESTIONS, ROUND_SIZE, TASKS, TOPICS

QUESTIONS_BY_KEY = {question['key']: question for question in QUESTIONS}
HISTORY_SIZE = 20
SECRETS = ['penguin', 'rocket', 'mango', 'lighthouse', 'origami', 'volcano', 'compass', 'saffron']


class AcademyWarmup(models.AbstractModel):
    _name = 'academy.warmup'
    _description = 'Academy Warm-up'

    def _state(self):
        user = self.env.user
        state = dict(user.academy_warmup or {})
        if not state:
            # when the learner begins: the apps they had already, the time
            Module = self.env['ir.module.module'].sudo()
            state = {'start': fields.Datetime.to_string(self.env.cr.now()),
                     'apps': Module.search([('application', '=', True), ('state', '=', 'installed')]).mapped('name'),
                     'tasks': {}}
            user.sudo().academy_warmup = state
        # the quiz of before rounds: its right answers are kept
        if 'answers' in state:
            state['right'] = sorted({*state.get('right', []),
                                     *(key for key, answer in state.pop('answers').items() if answer.get('correct'))})
        state.setdefault('right', [])
        state.setdefault('seen', {})
        state.setdefault('history', [])
        state.setdefault('round', None)
        state.setdefault('finds', {})
        if not state.get('secret'):
            # the word the console tells the learner, theirs
            state['secret'] = random.choice(SECRETS)
            self._save(state)
        return state

    def _save(self, state):
        self.env.user.sudo().academy_warmup = state

    def _steps_done(self):
        """ The steps the learner has done, as (course key, step) and (family, step). """
        done = set()
        for progress in self.env['academy.progress'].search([('user_id', '=', self.env.uid)]):
            course = COURSES_BY_KEY.get(progress.course_key)
            if not course:
                continue
            for step in progress._done_keys():
                done.add((course['key'], step))
                if course.get('family'):
                    done.add((course['family'], step))
        return done

    def _pool(self, topic):
        """ The questions of a topic the learner can answer. """
        done = self._steps_done()
        return [question for question in QUESTIONS
                if (topic == 'mixed' or question['topic'] == topic)
                and (not question['needs'] or tuple(question['needs']) in done)]

    def _round_payload(self, state):
        current = state['round']
        if not current:
            return False
        questions = []
        for item in current['questions']:
            question = QUESTIONS_BY_KEY.get(item['key'])
            if not question:
                continue
            options = [str(question['options'][index]) for index in item['order']]
            questions.append({'key': item['key'], 'question': str(question['question']), 'options': options,
                              'built': question['topic'] == 'built', 'answer': item.get('answer') or False})
        answered = [question for question in questions if question['answer']]
        return {
            'topic': current['topic'],
            'questions': questions,
            'score': sum(1 for question in answered if question['answer']['correct']),
            'finished': len(answered) == len(questions),
        }

    @api.model
    def academy_warmup(self):
        state = self._state()
        Module = self.env['ir.module.module'].sudo()
        apps = Module.search([('application', '=', True), ('state', '=', 'uninstalled')], order='shortdesc')
        history = state['history']
        return {
            'topics': [{'key': key, 'emoji': emoji, 'title': str(title), 'description': str(description),
                        'count': len(self._pool(key)),
                        'best': max(([round_['score'], round_['total']] for round_ in history if round_['topic'] == key),
                                    key=lambda best: best[0] / (best[1] or 1), default=None)}
                       for key, emoji, title, description in TOPICS],
            'round': self._round_payload(state),
            'history': history[-5:][::-1],
            'right': len(state['right']),
            'total': len(QUESTIONS),
            'tasks': [{'key': key, 'title': str(title), 'todo': str(todo), 'hint': str(hint),
                       'done': state['tasks'].get(key) or False}
                      for key, title, todo, hint in TASKS],
            'apps': [{'name': app.name, 'title': app.shortdesc} for app in apps],
            'finds': [{'key': key, 'title': str(title), 'what': str(what), 'todo': str(todo), 'hint': str(hint),
                       'placeholder': str(placeholder) if placeholder else False,
                       'done': state['finds'].get(key) or False}
                      for key, title, what, todo, hint, placeholder in FINDS],
            'secret': state['secret'],
        }

    @api.model
    def academy_warmup_start(self, topic='mixed'):
        """ A new round: the questions of the topic seen the least, shuffled, their options too. """
        if topic not in dict((key, True) for key, *_rest in TOPICS):
            raise UserError(_("This topic does not exist."))
        state = self._state()
        pool = self._pool(topic)
        if not pool:
            raise UserError(_("No question in this topic for you yet: do a few steps of a course first."))
        # the questions seen the least first, then those last got wrong; at random among equals
        random.shuffle(pool)
        pool.sort(key=lambda question: state['seen'].get(question['key'], 0))
        picked = pool[:ROUND_SIZE]
        random.shuffle(picked)
        questions = []
        for question in picked:
            order = list(range(len(question['options'])))
            random.shuffle(order)
            questions.append({'key': question['key'], 'order': order})
        state['round'] = {'topic': topic, 'questions': questions}
        self._save(state)
        return self.academy_warmup()

    @api.model
    def academy_warmup_answer(self, key, choice):
        """ The option ``choice``, as shown, answered: {'choice', 'correct', 'right', 'why', 'result'}. """
        state = self._state()
        item = next((item for item in (state['round'] or {}).get('questions', []) if item['key'] == key), None)
        if not item:
            raise UserError(_("This question is not in your round."))
        if item.get('answer'):
            return dict(item['answer'], result=False)
        question = QUESTIONS_BY_KEY[key]
        right = item['order'].index(question['right'])
        answer = {'choice': choice, 'correct': choice == right, 'right': right, 'why': str(question['why'])}
        item['answer'] = answer
        state['seen'][key] = state['seen'].get(key, 0) + 1
        self.env.user._academy_active()
        if answer['correct'] and key not in state['right']:
            state['right'].append(key)
        result = False
        current = self._round_payload(state)
        if current['finished']:
            total = len(current['questions'])
            best = max((round_['score'] for round_ in state['history']
                        if round_['topic'] == current['topic'] and round_['total'] == total), default=-1)
            state['history'] = (state['history'] + [{
                'date': fields.Date.to_string(fields.Date.context_today(self)), 'topic': current['topic'],
                'score': current['score'], 'total': total,
            }])[-HISTORY_SIZE:]
            result = {'score': current['score'], 'total': total, 'record': current['score'] > best >= 0}
        self._save(state)
        return dict(answer, result=result)

    @api.model
    def academy_warmup_check(self, key, value=None):
        """ Done? The task checked in the database: {'ok', 'message'}. """
        state = self._state()
        ok, message = getattr(self, '_check_' + key)(state, value)
        if ok:
            state['tasks'][key] = message
            self._save(state)
        return {'ok': ok, 'message': message}

    def _check_customer(self, state, value):
        partner = self.env['res.partner'].sudo().search([('name', '=ilike', 'odoo mates'),
                                                         ('email', '=ilike', 'odoomates@gmail.com')], limit=1)
        if partner:
            return True, _("Found it: %s, the contact you created. Thank you for adding us!", partner.display_name)
        if self.env['res.partner'].sudo().search_count([('name', '=ilike', 'odoo mates')]):
            return False, _("Odoo Mates is there, but not with the email odoomates@gmail.com: open it and set the email.")
        return False, _("No contact named Odoo Mates yet.")

    def _check_user(self, state, value):
        user = self.env['res.users'].sudo().search([('name', 'ilike', 'niyas')], limit=1)
        if user:
            return True, _("Found the user %(name)s, who logs in as %(login)s.", name=user.name, login=user.login)
        return False, _("No user named Niyas yet: Settings > Users & Companies > Users.")

    def _check_app(self, state, value):
        module = self.env['ir.module.module'].sudo().search([('name', '=', value)], limit=1)
        if not module:
            return False, _("Pick the app you installed in the list.")
        if module.state != 'installed':
            return False, _("%s is not installed yet: in Apps, click its Activate button.", module.shortdesc)
        if module.name in state['apps']:
            return False, _("%s was installed before you began: install another one.", module.shortdesc)
        return True, _("%s is installed: its menu is on your home screen.", module.shortdesc)

    def _check_chatter(self, state, value):
        if 'mail.message' not in self.env:
            return False, _("No chatter in this database yet: install Discuss first.")
        message = self.env['mail.message'].sudo().search([
            ('author_id', '=', self.env.user.partner_id.id), ('message_type', '=', 'comment'),
            ('model', '!=', False), ('res_id', '!=', False), ('create_date', '>=', state['start']),
        ], order='id desc', limit=1)
        if not message:
            return False, _("No message of yours in a chatter since you began the warm-up.")
        return True, _("Found your message on %(record)s (%(model)s).",
                       record=message.record_name or message.res_id, model=message.model)

    def _check_technical(self, state, value):
        if (value or '').strip().lower() == 'email':
            return True, _("email: the name in the code and in the database, where the label says Email.")
        return False, _("Not quite: in developer mode, hover the label Email of a contact.")

    # Find it: checked against the database

    @api.model
    def academy_warmup_find(self, key, value=None):
        """ Found? {'ok', 'message'} """
        if key not in dict((find[0], True) for find in FINDS):
            raise UserError(_("This task does not exist."))
        state = self._state()
        value = value if isinstance(value, bool) else (str(value or '')).strip()
        ok, message = getattr(self, '_find_' + key)(state, value)
        if ok:
            state['finds'][key] = message
            self._save(state)
        return {'ok': ok, 'message': message}

    def _find_console(self, state, value):
        if value.lower().strip('"\'') == state['secret']:
            return True, _("Right: you ran JavaScript in the console. Errors of Odoo's screens show there too.")
        return False, _("Not this word: type academy.secret() in the console of this tab.")

    def _find_debug(self, state, value):
        # the web client tells whether it runs in developer mode
        if value is True:
            return True, _("The developer mode is on: the bug icon is in the top bar.")
        return False, _("The developer mode is not on in this tab yet: activate it, then come back.")

    def _find_model(self, state, value):
        if value.lower() == 'res.users':
            return True, _("res.users: the model of the users. Its table is res_users.")
        if value.lower() == 'res.partner':
            return False, _("res.partner is the model of contacts: open a user, not a contact.")
        return False, _("Not quite: open a user, then the bug icon > Data.")

    def _find_record_id(self, state, value):
        if value == str(self.env.uid):
            return True, _("%s: the id of your user, the same in every table that links to it.", value)
        return False, _("Not your user's id: open your own user, and read the end of the address.")

    def _find_xmlid(self, state, value):
        expected = self.env.company.get_external_id().get(self.env.company.id)
        if expected and value == expected:
            return True, _("%s: in code, env.ref('%s') gives your company in any database.", value, value)
        return False, _("Not quite: open your company, then the bug icon > Metadata.")

    def _find_view_id(self, state, value):
        view = self.env['ir.ui.view'].sudo().browse(int(value)).exists() if value.isdigit() else None
        if view and view.model == 'res.users' and view.type == 'form':
            return True, _("View %(id)s: %(name)s, the form of the users.", id=view.id, name=view.name)
        if view:
            return False, _("View %(id)s is %(name)s, not the form of a user.", id=view.id, name=view.name)
        return False, _("No view with this id: open a user, then the bug icon > View: Form.")
