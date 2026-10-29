# Where each learner is in each course, and everything the Academy screen
# asks the server: the courses, a step with its code, and the actions of the
# two modes (write the files, install, check; build, undo), plus See it.
import base64
import difflib
import io
import os
import re
import zipfile

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.service import server
from odoo.modules.module import Manifest, get_module_path
from odoo.tools import config, file_open

import odoo.addons

from ..courses import COURSES, COURSES_BY_KEY
from .challenges import ChallengeChecker
from .code_checker import CodeChecker
from .hood import Hood
from .course_files import ICON, changed_lines, files_at
from .line_notes import line_note
from .live_builder import LiveBuilder, live_model

MODES = [('live', 'Build it live'), ('code', 'Code it')]
LEVELS = [('basic', 'Basic'), ('more', 'Basic + a little more')]
# the icons a learner can pick for their app, in static/img/icons
ICONS = ['book', 'car', 'bed', 'wrench', 'graduation', 'rocket', 'star', 'heart', 'leaf', 'bolt', 'cube',
         'tasks', 'users', 'calendar', 'flask']
COAUTHOR = 'Odoo Mates'
STORE_URL = 'https://apps.odoo.com/apps/modules/20.0/om_academy'


def dev_mode():
    """ The features of --dev Odoo runs with: [] when it does not. """
    return list(config['dev_mode'] or [])

README = """\
# %(name)s

The module `%(module)s` by %(author)s, built with the Odoo Mates Academy.

## Install it

1. Copy the folder `%(module)s` into an addons folder of your Odoo (a folder
   listed in `--addons-path`, next to your other modules).
2. Restart Odoo, then in Apps: *Update Apps List*, search "%(module)s", *Install*.

If you built this app live in the database you install it on, start the course
over in the Academy first: both would show a Library app.

## Keep building

Open the folder in your editor, change it, restart Odoo (or start it with
`--dev=reload,xml`) and upgrade the module. Happy coding!
"""


class AcademyProgress(models.Model):
    _name = 'academy.progress'
    _description = 'Academy Progress'
    _order = 'write_date desc'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user,
                              ondelete='cascade', index=True)
    course_key = fields.Char(required=True)
    mode = fields.Selection(MODES, default='live', required=True)
    level = fields.Selection(LEVELS, default='basic', required=True,
                             help="Basic + a little more adds the steps marked 'more' of the course.")
    current = fields.Integer(string='Current Step')
    done = fields.Json(default=list, help="The keys of the steps checked (Code it).")
    built = fields.Json(default=list, help="The keys of the steps built (Build it live), in order.")
    live_map = fields.Json(default=dict)
    live_log = fields.Json(default=dict)
    addons_path = fields.Char(help="Where Write it for me puts the learner's module.")
    # make it yours: the author of the module, and its icon
    author_name = fields.Char(help="The author of the learner's module: they write it before building.")
    coauthor = fields.Boolean(help="Odoo Mates signs the module too.")
    icon = fields.Char(default='book', help="The suggested icon picked, or 'custom' for the image uploaded.")
    icon_attachment_id = fields.Many2one('ir.attachment', help="The icon the learner uploaded.")
    challenges_done = fields.Json(default=list, help="The challenges of Your turn the learner did.")
    completed_on = fields.Date(help="When the learner completed the app: all its steps built or checked.")

    _user_course_unique = models.Constraint('UNIQUE(user_id, course_key)', "One progress per course and user.")

    #
    # helpers
    #

    @api.model
    def _course(self, course_key):
        course = COURSES_BY_KEY.get(course_key)
        if not course:
            raise UserError(_("This course does not exist."))
        return course

    @api.model
    def _get(self, course_key):
        self._course(course_key)
        progress = self.search([('user_id', '=', self.env.uid), ('course_key', '=', course_key)], limit=1)
        if progress:
            return progress
        # the author of their last course, for a start, and the icon of the subject
        last = self.search([('user_id', '=', self.env.uid)], limit=1)
        values = {'course_key': course_key, 'icon': self._course(course_key).get('default_icon') or 'book'}
        if last:
            values.update(author_name=last.author_name, coauthor=last.coauthor)
        return self.create(values)

    def _author(self):
        name = (self.author_name or '').strip()
        if not name:
            return ''  # the learner first: Odoo Mates is never the author alone
        return ', '.join(filter(None, [name, COAUTHOR if self.coauthor else None]))

    def _require_author(self):
        """ The learner is the author of their app: their name first. """
        if not (self.author_name or '').strip():
            raise UserError(_("Write your name first, in “What we will build” > “Make it yours”: "
                              "you are the author of this app."))

    def _icon_bytes(self):
        if self.icon == 'custom' and self.icon_attachment_id:
            raw = self.icon_attachment_id.raw
            return raw.content if hasattr(raw, 'content') else raw
        with file_open('om_academy/static/img/icons/%s.png' % (self.icon if self.icon in ICONS else 'book'), 'rb') as handle:
            return handle.read()

    def _icon_url(self):
        if self.icon == 'custom' and self.icon_attachment_id:
            return '/web/image/%d' % self.icon_attachment_id.id
        return '/om_academy/static/img/icons/%s.png' % (self.icon if self.icon in ICONS else 'book')

    def _personalize(self, path, content):
        """ A file of the course, made the learner's: their name as author of the
        manifest, their icon. """
        if content == ICON:
            return self._icon_bytes()
        if path == '__manifest__.py':
            return re.sub(r"(\n    'version': [^\n]*\n)", lambda match: "%s    'author': %r,\n" % (match.group(1), self._author()),
                          content, count=1)
        return content

    def _level_course(self):
        """ The course as this learner takes it: without the extra steps at the Basic level. """
        course = self._course(self.course_key)
        steps = [step for step in course['steps'] if self.level == 'more' or step.get('level') != 'more']
        icon = None
        personal = []
        for step in steps:
            files = {}
            for path, content in (step.get('files') or {}).items():
                if content == ICON:
                    icon = icon or self._icon_bytes()
                    files[path] = icon
                else:
                    files[path] = self._personalize(path, content)
            personal.append(dict(step, files=files) if 'files' in step else step)
        return dict(course, steps=personal)

    def _step_index(self, index):
        steps = self._level_course()['steps']
        if not 0 <= index < len(steps):
            raise UserError(_("This step does not exist."))
        return index

    def _done_keys(self):
        keys = set(self.built or ()) if self.mode == 'live' else set(self.done or ())
        # the last step, Your app is done, is done once all the others are
        steps = self._level_course()['steps']
        others = {step['key'] for step in steps if not step.get('intro') and not step.get('finish')}
        if others and others <= keys:
            keys |= {step['key'] for step in steps if step.get('finish')}
        return keys

    @api.model
    def _addons_paths(self):
        """ The addons folders a module can be written to: writable, and not Odoo's own. """
        paths = []
        for path in odoo.addons.__path__:
            path = os.path.realpath(path)
            if path in paths or not os.path.isdir(path) or not os.access(path, os.W_OK):
                continue
            if os.path.isdir(os.path.join(path, 'base')) or os.path.isdir(os.path.join(path, 'web')):
                continue
            paths.append(path)
        return paths

    def _default_path(self):
        """ Where Write it for me puts a module unless the learner picks a folder:
        the addons folder Odoo keeps for each user, when it can be written. Never
        a folder of other modules on its own: it may be a repository. """
        if self.addons_path:
            return self.addons_path
        data = os.path.realpath(config.addons_data_dir)
        return data if data in self._addons_paths() else None

    def _module_path(self):
        """ Where the learner's module is: where Odoo found it, else where Write it for me puts it. """
        course = self._course(self.course_key)
        found = get_module_path(course['module'], display_warning=False)
        if found:
            return found
        base = self._default_path()
        return os.path.join(base, course['module']) if base else None

    #
    # what the screen shows
    #

    @api.model
    def academy_home(self):
        progresses = {progress.course_key: progress for progress in self.search([('user_id', '=', self.env.uid)])}
        courses = []
        for course in COURSES:
            progress = progresses.get(course['key'])
            more = progress and progress.level == 'more'
            steps = [step for step in (progress._level_course() if progress else course)['steps']
                     if not step.get('intro') and (more or step.get('level') != 'more')]
            done = len(progress._done_keys() & {step['key'] for step in steps}) if progress else 0
            courses.append({
                'key': course['key'], 'name': str(course['name']), 'summary': str(course['summary']),
                'minutes': course['more_minutes'] if more else course['minutes'],
                'level': str(course['level']), 'steps': len(steps),
                'done': done, 'started': bool(progress), 'video_url': course.get('video_url') or False,
                'family': course.get('family') or False, 'subject': course.get('subject') or False,
                'icon_url': progress._icon_url() if progress else
                '/om_academy/static/img/icons/%s.png' % (course.get('default_icon') or 'book'),
            })
        last = self.search([('user_id', '=', self.env.uid)], limit=1)
        completed = [progress for progress in progresses.values() if progress.completed_on]
        return {'courses': courses, 'last': last.course_key if last else False,
                'welcome': not self.env.user.academy_welcomed,
                'shelf': [{'key': progress.course_key, 'name': progress._app_name(), 'icon_url': progress._icon_url(),
                           'date': fields.Date.to_string(progress.completed_on)}
                          for progress in sorted(completed, key=lambda progress: progress.completed_on)],
                'trophies': self._trophies(progresses)}

    @api.model
    def _trophies(self, progresses):
        """ The badges of the learner: [{'key', 'emoji', 'title', 'description', 'earned'}]. """
        completed = [progress for progress in progresses.values() if progress.completed_on]
        first_apps = [progress for progress in completed
                      if COURSES_BY_KEY[progress.course_key].get('family') == 'first_app']
        subjects = [course['key'] for course in COURSES if course.get('family') == 'first_app']
        warmup = self.env.user.academy_warmup or {}
        # the questions ever answered right, in any round (and in the quiz of before rounds)
        right = set(warmup.get('right') or ()) | {key for key, answer in (warmup.get('answers') or {}).items()
                                                  if answer.get('correct')}
        return [
            {'key': 'first_app', 'emoji': '🚀', 'title': _("First app"),
             'description': _("You built your first Odoo app."), 'earned': bool(first_apps)},
            {'key': 'more', 'emoji': '✨', 'title': _("A little more"),
             'description': _("An app with a chatter and the history of its changes."),
             'earned': any(progress.level == 'more' for progress in first_apps)},
            {'key': 'all_apps', 'emoji': '🏆', 'title': _("Every app"),
             'description': _("All %s apps of the first course.", len(subjects)),
             'earned': {progress.course_key for progress in first_apps} >= set(subjects)},
            {'key': 'extender', 'emoji': '🧩', 'title': _("Extender"),
             'description': _("You extended Odoo's own contacts."),
             'earned': any(progress.course_key == 'contacts' for progress in completed)},
            {'key': 'guardian', 'emoji': '🛡️', 'title': _("Guardian"),
             'description': _("You secured an app, the Odoo 20 way."),
             'earned': any(progress.course_key == 'security' for progress in completed)},
            {'key': 'coder', 'emoji': '💻', 'title': _("Coder"),
             'description': _("An app written in your own editor."),
             'earned': any(progress.mode == 'code' for progress in completed)},
            {'key': 'challenger', 'emoji': '🎯', 'title': _("Challenger"),
             'description': _("All the challenges of a course, on your own."),
             'earned': any(progress._challenges() and all(c['done'] for c in progress._challenges())
                           for progress in progresses.values())},
            {'key': 'warm', 'emoji': '🔥', 'title': _("Warmed up"),
             'description': _("12 right answers in the warm-up, or all its tasks done."),
             'earned': len(right) >= 12
                       or len(warmup.get('tasks') or {}) >= 5},
        ]

    def _learner_name(self):
        """ The learner's name alone: a co-author is no part of their certificate. """
        name = (self.author_name or self.user_id.name or '').strip()
        return re.sub(r',?\s*%s\s*$' % re.escape(COAUTHOR), '', name, flags=re.IGNORECASE).strip() or name

    def _app_name(self):
        course = self._course(self.course_key)
        return course.get('subject') or course.get('app_name') or str(course['name'])

    def _app_done(self):
        steps = [step['key'] for step in self._level_course()['steps'] if not step.get('intro')]
        return bool(steps) and set(steps) <= self._done_keys()

    def _mark_completed(self):
        if not self.completed_on and self._app_done():
            self.completed_on = fields.Date.context_today(self)

    def _certificate(self):
        """ What the certificate says. """
        def data_url(raw):
            return 'data:image/png;base64,' + base64.b64encode(raw).decode()
        with file_open('om_academy/static/description/icon.png', 'rb') as handle:
            academy_icon = handle.read()
        steps = [str(step['title']) for step in self._level_course()['steps']
                 if not step.get('intro') and not step.get('finish')]
        return {
            'name': self._learner_name(),
            'app': self._app_name(),
            'learned': ' · '.join(steps),
            'date': (self.completed_on or fields.Date.context_today(self)).strftime('%d %B %Y'),
            'how': _("written in their own editor") if self.mode == 'code' else _("built live in Odoo"),
            'academy_icon': data_url(academy_icon),
            'app_icon': data_url(self._icon_bytes()),
        }

    def _certificate_all(self):
        """ The certificate of all the courses completed: self, the progresses of a learner. """
        def data_url(raw):
            return 'data:image/png;base64,' + base64.b64encode(raw).decode()
        with file_open('om_academy/static/description/icon.png', 'rb') as handle:
            academy_icon = handle.read()
        completed = self.filtered('completed_on').sorted('completed_on')
        named = completed.filtered('author_name')
        progresses = {progress.course_key: progress for progress in self.search([('user_id', '=', self.env.uid)])}
        trophies = [trophy for trophy in self._trophies(progresses) if trophy['earned']]
        return {
            'name': named[-1:]._learner_name() if named else self.env.user.name,
            'count': len(completed),
            'apps': [{'name': progress._app_name(), 'course': str(progress._course(progress.course_key)['name']),
                      'date': progress.completed_on.strftime('%d %B %Y'), 'icon': data_url(progress._icon_bytes())}
                     for progress in completed],
            'trophies': '  ·  '.join('%s %s' % (trophy['emoji'], trophy['title']) for trophy in trophies),
            'date': (completed[-1:].completed_on or fields.Date.context_today(self)).strftime('%d %B %Y'),
            'academy_icon': data_url(academy_icon),
        }

    @api.model
    def academy_certificate_all(self):
        """ One certificate for all the courses the learner completed. """
        progresses = self.search([('user_id', '=', self.env.uid), ('completed_on', '!=', False)])
        if not progresses:
            raise UserError(_("Complete a course first: its certificate comes with the last step."))
        return self.env.ref('om_academy.action_report_certificate_all').report_action(progresses, config=False)

    @api.model
    def academy_certificate(self, course_key):
        progress = self._get(course_key)
        if not progress.completed_on:
            raise UserError(_("Complete the app first: the certificate comes with the last step."))
        # the certificate has no company layout: no wizard to set one up first
        return self.env.ref('om_academy.action_report_certificate').report_action(progress, config=False)

    @api.model
    def academy_certificate_behind(self, what):
        """ Behind the certificate: its report record, or its QWeb template, opened in Odoo. """
        record = self.env.ref('om_academy.action_report_certificate' if what == 'report'
                              else 'om_academy.report_certificate')
        return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id,
                'views': [[False, 'form']], 'target': 'current'}

    @api.model
    def academy_welcomed(self):
        """ The learner went through the welcome guide: it opens on its own no more. """
        self.env.user.sudo().academy_welcomed = True
        return True

    @api.model
    def academy_open(self, course_key):
        progress = self._get(course_key)
        notice = progress._forget_if_uninstalled()
        progress._ensure_module()
        progress._mark_completed()
        return dict(progress._course_payload(), notice=notice)

    def _ensure_module(self):
        """ An app built live before the Academy made modules of them gets its module. """
        module = self._course(self.course_key)['module']
        if self.mode != 'live' or not self.built:
            return
        if 'module:' + module in (self.live_map or {}):
            self._live().refresh_module()
            return
        course = self._level_course()
        indexes = [index for index, step in enumerate(course['steps']) if step['key'] in self.built]
        live = self._live()
        live._sync_module(self.built[0], max(indexes))
        live.refresh_module()
        live.save()

    def _forget_if_uninstalled(self):
        """ The app built live was uninstalled from Apps, and all it built with it:
        the course starts over. """
        module = self._course(self.course_key)['module']
        entry = (self.live_map or {}).get('module:' + module)
        if not entry or self.env['ir.module.module'].sudo().browse(entry[1]).exists():
            return False
        self.write({'built': [], 'live_map': {}, 'live_log': {}, 'current': 0})
        return _("You uninstalled %s from Apps, and with it everything built live: the course "
                 "starts over.", module)

    def _levels(self):
        """ The two levels of a course that has extra steps, to choose between: what
        each builds, the extra steps marked. """
        course = self._course(self.course_key)
        if not any(step.get('level') == 'more' for step in course['steps']):
            return []
        needs = [name for name in course.get('more_depends') or ()
                 if not self.env['ir.module.module'].sudo().search_count([('name', '=', name),
                                                                          ('state', '=', 'installed')])]
        steps = [step for step in course['steps'] if not step.get('intro') and not step.get('finish')]
        return [
            {'key': 'basic', 'label': str(dict(LEVELS)['basic']), 'minutes': course['minutes'],
             'steps': [str(step['title']) for step in steps if step.get('level') != 'more'],
             'extra': [], 'installs': []},
            {'key': 'more', 'label': str(dict(LEVELS)['more']), 'minutes': course['more_minutes'],
             'steps': [str(step['title']) for step in steps if step.get('level') != 'more'],
             'extra': [str(step['title']) for step in steps if step.get('level') == 'more'],
             'installs': needs},
        ]

    def _course_payload(self):
        course = self._level_course()
        done = self._done_keys()
        return {
            'key': course['key'], 'name': str(course['name']), 'module': course['module'],
            'family': course.get('family') or False, 'mode': self.mode, 'current': self.current, 'level': self.level, 'levels': self._levels(),
            'author_name': self.author_name or '', 'coauthor': self.coauthor,
            'share_url': STORE_URL,
            'app_name': course.get('subject') or course.get('app_name') or str(course['name']),
            'author': self._author(), 'coauthor_name': COAUTHOR,
            # Restart Odoo from the Academy: in developer mode, for administrators
            'can_restart': bool(dev_mode()) and self.env.user.has_group('base.group_system'),
            'auto_reload': 'reload' in dev_mode(),
            'icon': self.icon, 'icon_url': self._icon_url(), 'icons': ICONS,
            'steps': [{'index': index, 'key': step['key'], 'title': str(step['title']),
                       'done': step['key'] in done, 'intro': bool(step.get('intro')),
                       'more': step.get('level') == 'more'}
                      for index, step in enumerate(course['steps'])],
            'addons_paths': self._addons_paths(),
            'addons_path': self._default_path() or False,
            'module_path': self._module_path() or False,
            'module_path_found': bool(get_module_path(course['module'], display_warning=False)),
            'can_undo': bool(self.built),
            'last_built': self.built[-1] if self.built else False,
        }

    @api.model
    def academy_step(self, course_key, index):
        progress = self._get(course_key)
        index = progress._step_index(index)
        progress.current = index
        course = progress._level_course()
        step = course['steps'][index]
        step_files = step.get('files') or {}
        files = []
        for path, content in step_files.items():
            if not isinstance(content, str):
                files.append({'path': '%s/%s' % (course['module'], path), 'content': '', 'empty': False,
                              'image': progress._icon_url(), 'lines': []})
                continue
            new = changed_lines(course, index, path)
            lines = content.splitlines()
            files.append({
                'path': '%s/%s' % (course['module'], path),
                'content': content,
                'empty': not content,
                'image': False,
                'lines': [{'number': number + 1, 'text': text, 'new': number in new,
                           'note': str(line_note(text) or '') or False,
                           # the learner writes their name there, in the code
                           'author': path == '__manifest__.py' and text.lstrip().startswith("'author':")}
                          for number, text in enumerate(lines)],
            })
        built = step['key'] in (progress.built or ())
        done = step['key'] in progress._done_keys()
        previous_built = all(other['key'] in (progress.built or ()) or other.get('intro')
                             for other in course['steps'][:index])
        return {
            'index': index,
            'key': step['key'],
            'title': str(step['title']),
            'explain': Markup(str((progress.level == 'more' and step.get('explain_more')) or step['explain'])),
            'intro': bool(step.get('intro')),
            'finish': bool(step.get('finish')),
            'preview': (progress.level == 'more' and step.get('preview_more')) or step.get('preview') or False,
            # what the learner sees in Odoo once the step is built or checked
            'result_gif': step.get('result_gif') or False,
            'files': files,
            'tree': progress._file_tree(course, index),
            'live_note': Markup(str(step['live_note'])) if step.get('live_note') else False,
            'code_note': Markup(str(step['code_note'])) if step.get('code_note') else False,
            'see_text': str(step['see_text']) if step.get('see_text') else False,
            # See it opens what the step made: once built, or once checked
            'can_see': bool(step.get('see')) and (
                built if progress.mode == 'live' else step['key'] in (progress.done or ())),
            'can_see_after_check': bool(step.get('see')),
            'done': done,
            'built': built,
            'previous_built': previous_built,
            'is_last_built': bool(progress.built) and progress.built[-1] == step['key'],
            'completed': bool(progress.completed_on),
            # Python changed: Odoo loads it when it starts (the manifest is read again on Upgrade)
            'python_changed': any(path.endswith('.py') and path != '__manifest__.py' for path in step_files),
            'challenges': progress._challenges() if step.get('finish') else [],
            'buildable': not step.get('intro') and not step.get('finish'),
            'mode': progress.mode,
        }

    @api.model
    def _file_tree(self, course, index):
        """ Every file of the module up to the step, as it is after the step:
        [{'path', 'status', 'image', 'lines'}], the status 'new' when the step adds
        it, 'changed' when it rewrites it, else 'same'; the lines the step adds are new. """
        before, contents = set(), {}
        for step in course['steps'][:index]:
            before.update(step.get('files') or ())
            contents.update(step.get('files') or {})
        now = course['steps'][index].get('files') or {}
        contents.update(now)
        tree = []
        for path in sorted(contents, key=lambda path: ('/' in path, path)):
            content = contents[path]
            new = changed_lines(course, index, path) if path in now and isinstance(content, str) else ()
            tree.append({
                'path': path,
                'status': 'same' if path not in now else 'changed' if path in before else 'new',
                'image': self._icon_url() if not isinstance(content, str) else False,
                'lines': [{'number': number + 1, 'text': text, 'new': number in new}
                          for number, text in enumerate(content.splitlines())]
                         if isinstance(content, str) else [],
            })
        return tree

    #
    # actions shared by the modes
    #

    @api.model
    def academy_set_mode(self, course_key, mode):
        if mode not in dict(MODES):
            raise UserError(_("Unknown mode."))
        progress = self._get(course_key)
        progress.mode = mode
        return progress._course_payload()

    def _challenges(self):
        course = self._course(self.course_key)
        hint = 'hint_live' if self.mode == 'live' else 'hint_code'
        return [{'key': challenge['key'], 'title': str(challenge['title']), 'todo': str(challenge['todo']),
                 'hint': str(challenge[hint]), 'done': challenge['key'] in (self.challenges_done or [])}
                for challenge in course.get('challenges') or []]

    @api.model
    def academy_challenge_check(self, course_key, key):
        """ Your turn: is the challenge done? {'ok', 'message', 'all_done'} """
        progress = self._get(course_key)
        course = progress._course(course_key)
        challenge = next((challenge for challenge in course.get('challenges') or [] if challenge['key'] == key), None)
        if not challenge:
            raise UserError(_("This challenge does not exist."))
        ok, message = ChallengeChecker(progress, course).check(challenge)
        if ok and key not in (progress.challenges_done or []):
            progress.challenges_done = list(progress.challenges_done or []) + [key]
        keys = {challenge['key'] for challenge in course['challenges']}
        return {'ok': ok, 'message': message, 'all_done': keys <= set(progress.challenges_done or [])}

    @api.model
    def academy_hood(self, course_key, index):
        """ Under the hood: what the step made in the database, read live. """
        progress = self._get(course_key)
        course = progress._level_course()
        index = progress._step_index(index)
        if course['steps'][index].get('intro') or course['steps'][index].get('finish'):
            return {'tables': [], 'records': []}
        return Hood(progress, course, index).build()

    @api.model
    def academy_set_level(self, course_key, level):
        """ Basic, or Basic + a little more. Going back to Basic undoes the extra
        steps built; picking more installs what they need (Discuss for the chatter). """
        if level not in dict(LEVELS):
            raise UserError(_("Unknown level."))
        progress = self._get(course_key)
        course = self._course(course_key)
        if level == 'basic':
            extra = {step['key'] for step in course['steps'] if step.get('level') == 'more'}
            live = progress._live()
            for step_key in reversed(progress.built or []):
                if step_key in extra:
                    live.undo(step_key)
            progress.write({
                'built': [key for key in progress.built or [] if key not in extra],
                'done': [key for key in progress.done or [] if key not in extra],
            })
        progress.write({'level': level, 'current': 0})
        if level == 'more':
            Module = self.env['ir.module.module'].sudo()
            missing = Module.search([('name', 'in', course.get('more_depends') or []), ('state', '!=', 'installed')])
            if missing:
                missing.button_immediate_install()
                action = self.env.ref('om_academy.academy_action')
                return {'type': 'ir.actions.client', 'tag': 'reload', 'params': {'action_id': action.id}}
        return progress._course_payload()

    @api.model
    def academy_set_identity(self, course_key, values):
        """ Make it yours: {'author_name', 'coauthor', 'icon'}, or {'icon_data': the
        base64 of an image uploaded}. The app built live takes the new icon. """
        progress = self._get(course_key)
        update = {key: values[key] for key in ('author_name', 'coauthor') if key in values}
        if values.get('icon') in ICONS:
            update['icon'] = values['icon']
        if values.get('icon_data'):
            raw = base64.b64decode(values['icon_data'])
            if len(raw) > 1024 * 1024:
                raise UserError(_("The icon is too big: 1 MB at most."))
            attachment = self.env['ir.attachment'].create({
                'name': 'icon.png', 'raw': raw, 'res_model': self._name, 'res_id': progress.id,
            })
            if not attachment.mimetype.startswith('image/'):
                attachment.unlink()
                raise UserError(_("This file is not an image: pick a PNG."))
            progress.icon_attachment_id.unlink()
            update.update(icon='custom', icon_attachment_id=attachment.id)
        progress.write(update)
        live = progress._live()
        module = live.record('module:' + progress._course(course_key)['module'])
        if module:
            module.author = progress._author() or False
        if 'icon' in update:
            live.set_app_icon()
        return progress._course_payload()

    @api.model
    def academy_see_url(self, course_key, index):
        """ See it in Odoo, in a tab of its own: the address of what the step made. """
        action = self.academy_see(course_key, index)
        action_id = action.get('id')
        if not action_id:
            # a record of Odoo's own technical models: their menu's action
            xmlid = {'ir.module.module': 'base.open_module_tree', 'ir.model': 'base.action_model_model'}.get(
                action.get('res_model'))
            action_id = self.env.ref(xmlid).id if xmlid else None
        if not action_id:
            return False
        return '/odoo/action-%s%s' % (action_id, '/%s' % action['res_id'] if action.get('res_id') else '')

    @api.model
    def academy_see(self, course_key, index):
        """ The action opening, in Odoo, what the step made. """
        progress = self._get(course_key)
        course = progress._level_course()
        step = course['steps'][progress._step_index(index)]
        model = course['main_model']
        action_ref = course['main_action']
        if progress.mode == 'live':
            live = progress._live()
            ir_model = live.ir_model(model) if (model in self.env or live.record('model:' + model)) else None
            model_name = live.model_name(model)
            action = self.env.ref(action_ref) if '.' in action_ref else live.record(action_ref)
        else:
            ir_model = self.env['ir.model']._get(model) if model in self.env else None
            model_name = model
            action = self.env.ref(action_ref if '.' in action_ref else '%s.%s' % (course['module'], action_ref),
                                  raise_if_not_found=False)
        kind = step.get('see')
        if kind == 'module':
            module = self.env['ir.module.module'].search([('name', '=', course['module'])], limit=1)
            if not module:
                raise UserError(_("Odoo does not know your module yet: click Install first."))
            return {'type': 'ir.actions.act_window', 'res_model': 'ir.module.module', 'res_id': module.id,
                    'views': [[False, 'form']], 'target': 'current'}
        if kind in ('model', 'model_access'):
            if not ir_model:
                raise UserError(_("The model does not exist yet: finish this step first."))
            return {'type': 'ir.actions.act_window', 'res_model': 'ir.model', 'res_id': ir_model.id,
                    'views': [[False, 'form']], 'target': 'current'}
        if not action:
            raise UserError(_("The app has no menu yet: finish the step 'An action and a menu' first."))
        xmlid = action.get_external_id().get(action.id)
        result = self.env['ir.actions.act_window']._for_xml_id(xmlid) if xmlid else {
            'type': 'ir.actions.act_window', 'id': action.id, 'name': action.name, 'res_model': action.res_model,
            'views': [[False, 'list'], [False, 'form']], 'target': 'current'}
        if kind == 'form':
            record = self.env[model_name].search([], limit=1) if model_name in self.env else None
            result.update(views=[[False, 'form']], res_id=record.id if record else False)
        return result

    @api.model
    def academy_reset(self, course_key, keep=False):
        """ Start the course over. Built live: the app is uninstalled, or kept (it
        stays in Apps, the learner uninstalls it there when they like, and the
        Academy lets go of it). In Code it: the module is uninstalled, or kept
        installed; the learner's files stay in their folder. """
        progress = self._get(course_key)
        module_name = progress._course(course_key)['module']
        if progress.mode == 'live' and keep:
            progress._live().refresh_module()  # its Installed Features, as it is left
            progress.write({'built': [], 'done': [], 'current': 0, 'live_map': {}, 'live_log': {},
                            'challenges_done': [], 'completed_on': False})
            return progress._course_payload()
        progress._reset()
        module = self.env['ir.module.module'].sudo().search([('name', '=', module_name), ('state', '=', 'installed')])
        if progress.mode == 'code' and module and not keep:
            module.button_immediate_uninstall()
            action = self.env.ref('om_academy.academy_action')
            return {'type': 'ir.actions.client', 'tag': 'reload', 'params': {'action_id': action.id}}
        return progress._course_payload()

    def _reset(self):
        """ Undo everything built live, and start over. """
        for progress in self:
            live = progress._live()
            for step_key in reversed(progress.built or []):
                live.undo(step_key)
            progress.write({'built': [], 'done': [], 'current': 0, 'live_map': {}, 'live_log': {},
                            'challenges_done': [], 'completed_on': False})

    #
    # Build it live
    #

    def _live(self):
        return LiveBuilder(self, self._level_course())

    @api.model
    def academy_build(self, course_key, index):
        """ Build the step, and the steps before it not built yet. """
        progress = self._get(course_key)
        progress._require_author()
        course = progress._level_course()
        index = progress._step_index(index)
        built = list(progress.built or [])
        for position, step in enumerate(course['steps'][:index + 1]):
            if step.get('intro') or step['key'] in built:
                continue
            if not step.get('finish'):
                progress._live().build(position)
            built.append(step['key'])
            progress.built = built
        progress._mark_completed()
        return progress.academy_step(course_key, index) | {'course': progress._course_payload()}

    @api.model
    def academy_undo(self, course_key):
        """ Undo the last step built. """
        progress = self._get(course_key)
        built = list(progress.built or [])
        if not built:
            raise UserError(_("Nothing to undo."))
        step_key = built.pop()
        progress._live().undo(step_key)
        progress.built = built
        return progress._course_payload()

    #
    # Code it
    #

    @api.model
    def academy_set_path(self, course_key, path):
        progress = self._get(course_key)
        if path not in self._addons_paths():
            raise UserError(_("This folder is not a writable addons path of Odoo."))
        progress.addons_path = path
        return progress._course_payload()

    @api.model
    def academy_write(self, course_key, index):
        """ Write it for me: the files of the module as the step leaves them. """
        progress = self._get(course_key)
        progress._require_author()
        course = progress._level_course()
        index = progress._step_index(index)
        target = progress._module_path()
        if not target:
            raise UserError(_("Pick the addons folder where your module goes first."))
        root = os.path.realpath(target)
        written = []
        for path, content in files_at(course, index).items():
            full = os.path.realpath(os.path.join(root, path))
            if not full.startswith(root + os.sep):
                raise UserError(_("A file of the course would be written outside of the module."))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if isinstance(content, str):
                with open(full, 'w', encoding='utf-8') as handle:
                    handle.write(content)
            else:
                with open(full, 'wb') as handle:
                    handle.write(content)
            written.append(path)
        return {'path': root, 'files': written}

    @api.model
    def academy_restart(self):
        """ Restart Odoo, for the Python of a step: on a computer to learn on, never
        on a server people work on. So only in developer mode, and for administrators. """
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only administrators may restart Odoo."))
        if not dev_mode():
            raise UserError(_("Odoo restarts from the Academy in developer mode only: start it with "
                              "--dev=reload, and it restarts by itself when you save a Python file."))
        # once this answer is sent
        self.env.cr.postcommit.add(server.restart)
        return True

    @api.model
    def academy_install(self, course_key):
        """ Install the learner's module, or upgrade it, then come back to the Academy. """
        course = self._course(course_key)
        # Odoo keeps the manifests it read: the learner's one changes at every step
        Manifest._get_manifest_from_addons.cache_clear()
        Module = self.env['ir.module.module'].sudo()
        Module.update_list()
        module = Module.search([('name', '=', course['module'])], limit=1)
        if not module:
            raise UserError(_("Odoo does not find the module %s in its addons path.", course['module']))
        if module.state == 'installed':
            module.button_immediate_upgrade()
        else:
            module.button_immediate_install()
        action = self.env.ref('om_academy.academy_action')
        return {'type': 'ir.actions.client', 'tag': 'reload', 'params': {'action_id': action.id}}

    #
    # the finish: export, continue in code, compare
    #

    def _last_index(self):
        """ The last step this learner reached: built (live) or checked (code). """
        course = self._level_course()
        reached = self._done_keys()
        indexes = [index for index, step in enumerate(course['steps']) if step['key'] in reached]
        return max(indexes) if indexes else None

    @api.model
    def academy_export(self, course_key):
        """ Export as app: the module of the steps reached, as a zip to download. """
        progress = self._get(course_key)
        course = progress._level_course()
        index = progress._last_index()
        if index is None:
            raise UserError(_("Build or check a step first: there is nothing to export yet."))
        module = course['module']
        files = dict(files_at(course, index))
        files['README.md'] = README % {'module': module, 'name': str(course['name']),
                                       'author': progress._author() or _('you')}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path, content in sorted(files.items()):
                archive.writestr('%s/%s' % (module, path), content)
        attachment = self.env['ir.attachment'].create({
            'name': '%s.zip' % module,
            'raw': buffer.getvalue(),
            'mimetype': 'application/zip',
            'res_model': self._name,
            'res_id': progress.id,
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%d?download=true' % attachment.id,
                'target': 'download'}

    @api.model
    def academy_continue(self, course_key):
        """ Continue in code: the module of the steps built, written in the addons
        folder, and the course switched to Code it. """
        progress = self._get(course_key)
        index = progress._last_index()
        if progress.mode != 'live' or index is None:
            raise UserError(_("Build a step live first."))
        written = progress.academy_write(course_key, index)
        built = progress.built
        # the app built live makes room for the module: both would be the same app
        live = progress._live()
        for step_key in reversed(built):
            live.undo(step_key)
        progress.write({'mode': 'code', 'built': [], 'live_map': {}, 'live_log': {},
                        'done': [key for key in progress.done or [] if key in built]})
        return dict(written, course=progress._course_payload(), index=index)

    @api.model
    def academy_compare(self, course_key, index):
        """ The learner's files next to the course's: [{path, status, lines}], a
        line being {'kind': ' ', '+' or '-', 'text'}; '+' is what the course has
        and the learner's file lacks. """
        progress = self._get(course_key)
        course = progress._level_course()
        index = progress._step_index(index)
        root = progress._module_path()
        result = []
        for path, reference in sorted(files_at(course, index).items()):
            full = os.path.join(root, path) if root else None
            if not full or not os.path.isfile(full):
                result.append({'path': path, 'status': 'missing', 'lines': []})
                continue
            if not isinstance(reference, str):
                result.append({'path': path, 'status': 'same', 'lines': []})
                continue
            with open(full, encoding='utf-8') as handle:
                mine = handle.read()
            if mine.strip() == reference.strip():
                result.append({'path': path, 'status': 'same', 'lines': []})
                continue
            lines = []
            for line in difflib.unified_diff(mine.splitlines(), reference.splitlines(), lineterm='', n=2):
                if line.startswith(('---', '+++')):
                    continue
                kind = line[0] if line[:1] in '+- ' else '@'
                lines.append({'kind': kind, 'text': line[1:] if kind != '@' else line})
            result.append({'path': path, 'status': 'differs', 'lines': lines})
        return result

    @api.model
    def academy_check(self, course_key, index):
        progress = self._get(course_key)
        course = progress._level_course()
        index = progress._step_index(index)
        results = CodeChecker(self.env, course).check(index)
        passed = all(result['ok'] for result in results)
        if passed:
            done = list(progress.done or [])
            for step in course['steps'][:index + 1]:
                if step['key'] not in done:
                    done.append(step['key'])
            progress.done = done
            progress._mark_completed()
        return {'results': results, 'passed': passed, 'course': progress._course_payload()}
