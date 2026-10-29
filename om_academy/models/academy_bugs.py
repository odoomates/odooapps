# The bug hunt, as the Academy screen asks it: the bugs, one after the other,
# and the reason the learner picks for each, checked here. What they found is
# kept on their user.
from odoo import _, api, models
from odoo.exceptions import UserError

from .bugs import BUGS, BUGS_BY_KEY


class AcademyBugs(models.AbstractModel):
    _name = 'academy.bugs'
    _description = 'Academy Bug Hunt'

    def _state(self):
        state = dict(self.env.user.academy_bugs or {})
        state.setdefault('found', [])
        state.setdefault('tries', {})
        return state

    @api.model
    def academy_bugs(self):
        state = self._state()
        return {
            'bugs': [{'key': bug['key'], 'title': str(bug['title']), 'path': bug['path'], 'code': bug['code'],
                      'error': bug['error'], 'options': [str(option) for option in bug['options']],
                      'hint': str(bug['hint']), 'found': bug['key'] in state['found'],
                      'tries': state['tries'].get(bug['key'], 0),
                      # once found, the answer stays shown
                      'answer': self._answer(bug) if bug['key'] in state['found'] else False}
                     for bug in BUGS],
            'found': len(state['found']),
        }

    def _answer(self, bug):
        return {'right': bug['right'], 'why': str(bug['why']), 'fix': bug['fix']}

    @api.model
    def academy_bug_answer(self, key, choice):
        """ The reason picked: {'correct', 'right', 'why', 'fix'} when right, {'correct', 'hint'} else. """
        bug = BUGS_BY_KEY.get(key)
        if not bug:
            raise UserError(_("This bug does not exist."))
        state = self._state()
        self.env.user._academy_active()
        if choice != bug['right']:
            state['tries'][key] = state['tries'].get(key, 0) + 1
            self.env.user.sudo().academy_bugs = state
            return {'correct': False, 'choice': choice, 'hint': str(bug['hint'])}
        if key not in state['found']:
            state['found'].append(key)
        self.env.user.sudo().academy_bugs = state
        return dict(self._answer(bug), correct=True, choice=choice,
                    all_found=len(state['found']) == len(BUGS))
