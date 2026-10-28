# Health Check of the access profiles, run by hand or every week: the rules
# that silently disappeared (the database deletes a rule with the menu, the
# data or the field it names, without a version knowing it), the rules naming
# a button, tab or filter no view has any more, the record filters and
# conditions that no longer evaluate, and the allowed records gone. It reports,
# it never changes a profile: an access manager decides.
import json

from lxml import etree
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .om_access_profile_element import settings_app
from .om_access_version import LISTS, SINGLE_REFS

# the lists whose lines the database deletes on its own, with the model of their references
REF_LISTS = {
    'groups': 'res.groups',
    'granted_groups': 'res.groups',
    'hidden_menus': 'ir.ui.menu',
    'hidden_reports': 'ir.actions.report',
    'hidden_server_actions': 'ir.actions.server',
    'hidden_window_actions': 'ir.actions.act_window',
}
LINE_LISTS = ('models', 'menu_rules', 'fields', 'buttons', 'elements')
# the nodes of the views a button or element rule names, per kind of rule
NODE_TAGS = {'page': 'page', 'filter': 'filter', 'settings': 'app'}

ISSUE_KINDS = [
    ('lost', 'Rule Lost'),
    ('unmatched', 'Matches Nothing'),
    ('broken', 'Broken Filter'),
    ('missing', 'Record Gone'),
]


class OmAccessHealthIssue(models.Model):
    _name = 'om.access.health.issue'
    _description = 'Access Profile Health Issue'
    _order = 'profile_id, kind, id'

    profile_id = fields.Many2one('om.access.profile', string='Profile', required=True,
                                 ondelete='cascade', index=True, readonly=True)
    kind = fields.Selection(ISSUE_KINDS, required=True, readonly=True)
    rule = fields.Char(string='Rules', readonly=True)
    name = fields.Char(string='Rule', readonly=True)
    details = fields.Char(readonly=True)
    restorable = fields.Boolean(
        readonly=True,
        help="What the rule named exists again: restoring the last version brings the rule back.")
    # the line at fault, for the issues about a line still there
    res_model = fields.Char(readonly=True)
    res_id = fields.Many2oneReference(model_field='res_model', readonly=True)

    def _om_key(self):
        return (self.kind, self.rule or '', self.name or '')

    def action_open_profile(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.access.profile',
            'res_id': self.profile_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_restore(self):
        """ Restore the last version of the profiles: the rules lost since come
        back, those whose menu, data or field is still gone are listed. """
        for profile in self.profile_id:
            last = profile.version_ids[:1]
            if last and not last.is_current:
                last.action_restore()
        profiles = self.profile_id
        profiles._om_health_check()
        return self._om_reload()

    def action_remove(self):
        """ Remove the rule at fault, or accept the rules lost: the profile is
        saved as it is now, as a new version. """
        for issue in self:
            if issue.kind == 'lost':
                issue.profile_id._om_version_later()
            elif issue.res_model and issue.res_id:
                self.env[issue.res_model].browse(issue.res_id).exists().unlink()
        lost = self.filtered(lambda issue: issue.kind == 'lost').profile_id
        # accepting one lost rule accepts all those of its profile
        (self | self.search([('profile_id', 'in', lost.ids), ('kind', '=', 'lost')])).unlink()
        return self._om_reload()

    def _om_reload(self):
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}

    @api.model
    def _om_issues_action(self, profiles):
        action = self.env['ir.actions.act_window']._for_xml_id('om_access_manager.om_access_health_issue_action')
        action['domain'] = [('profile_id', 'in', profiles.ids)]
        return action


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    health_issue_ids = fields.One2many('om.access.health.issue', 'profile_id', string='Health Issues')
    health_issue_count = fields.Integer(string='Health Issue Count', compute='_compute_health_issue_count')

    @api.depends('health_issue_ids')
    def _compute_health_issue_count(self):
        counts = {group['profile_id'][0]: group['profile_id_count'] for group in self.env[
            'om.access.health.issue']._read_group([('profile_id', 'in', self.ids)], ['profile_id'], ['profile_id'])}
        for profile in self:
            profile.health_issue_count = counts.get(profile.id, 0)

    #
    # entry points
    #

    def action_health_check(self):
        """ Check these profiles (all of them from the menu) and show what is wrong. """
        profiles = self or self.with_context(active_test=False).search([])
        issues = profiles._om_health_check()
        if not issues:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'success',
                    'title': _("All good"),
                    'message': _("Every rule of %s still applies as it was set.",
                                 profiles.name if len(profiles) == 1 else _("the profiles checked")),
                    'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                },
            }
        return self.env['om.access.health.issue']._om_issues_action(profiles)

    @api.model
    def _cron_health_check(self):
        self.with_context(active_test=False).search([])._om_health_check()

    def _om_health_check(self):
        """ Replace the issues of these profiles by what is wrong now; tell each
        profile what is new in its chatter. Return the issues. """
        Issue = self.env['om.access.health.issue'].sudo()
        found = Issue
        for profile in self.sudo():
            known = {issue._om_key() for issue in profile.health_issue_ids}
            profile.health_issue_ids.unlink()
            issues = Issue.create([dict(values, profile_id=profile.id) for values in profile._om_health_issues()])
            new = issues.filtered(lambda issue: issue._om_key() not in known)
            if new:
                profile.message_post(body=profile._om_health_html(new), subtype_xmlid='mail.mt_note')
            found |= issues
        return found.sudo(False)

    def _om_health_html(self, issues):
        labels = dict(self.env['om.access.health.issue']._fields['kind']._description_selection(self.env))
        return Markup('<p>%s</p><ul>%s</ul>') % (
            _("The Health Check found what needs a look:"),
            Markup('').join(
                Markup('<li><b>%s</b>: %s%s</li>') % (
                    labels[issue.kind], ' / '.join(filter(None, [issue.rule, issue.name])),
                    Markup(' <span class="text-muted">(%s)</span>') % issue.details if issue.details else '')
                for issue in issues))

    #
    # what is wrong
    #

    def _om_health_issues(self):
        self.ensure_one()
        return [*self._om_health_lost(), *self._om_health_unmatched(),
                *self._om_health_broken(), *self._om_health_missing()]

    @api.model
    def _om_health_ref_ident(self, ref):
        if not isinstance(ref, dict):
            return ref
        return ref.get('xmlid') or ref.get('path') or ref.get('name')

    @api.model
    def _om_health_line_ident(self, key, line):
        identity = LISTS[key][2]
        if key == 'buttons' and line.get('button_type') == 'action':
            # an action button carries its action, which a version cannot tell from a removed one
            identity = ('model', 'button_type', 'button_label', 'view_type', 'button_id')
        return json.dumps([self._om_health_ref_ident(line.get(name)) for name in identity])

    def _om_health_lost(self):
        """ The rules the last version had and the profile no longer has: every
        change made by hand is saved as a version, so these went with what they named. """
        last = self.version_ids[:1]
        if not last:
            return []
        before, now = json.loads(last.data), self._om_version_data()
        Profile = self.env['om.access.profile']
        issues = []

        def lost(key, label, restorable):
            issues.append({
                'kind': 'lost', 'rule': self._om_field_label(Profile._name, LISTS[key][0]),
                'name': label, 'restorable': restorable,
            })

        for key, model_name in REF_LISTS.items():
            current = {self._om_health_ref_ident(ref) for ref in now.get(key) or []}
            for ref in before.get(key) or []:
                if self._om_health_ref_ident(ref) not in current:
                    lost(key, self._om_ref_label(ref), bool(self._om_find(ref, model_name)))
        for key in LINE_LISTS:
            current = {self._om_health_line_ident(key, line) for line in now.get(key) or []}
            for line in before.get(key) or []:
                if self._om_health_line_ident(key, line) not in current:
                    lost(key, self._om_line_label(key, line), self._om_health_findable(key, line))
        for key, field_name in SINGLE_REFS.items():
            if before.get(key) and not now.get(key):
                issues.append({
                    'kind': 'lost', 'rule': self._om_field_label(Profile._name, field_name),
                    'name': self._om_ref_label(before[key]),
                    'restorable': bool(self._om_find(before[key], 'ir.actions.act_window')),
                })
        return issues

    def _om_health_findable(self, key, line):
        """ Whether what a lost line named exists again on this database. """
        model_name = line.get('model')
        if key == 'menu_rules':
            return bool(self._om_find(line.get('menu'), 'ir.ui.menu'))
        if model_name not in self.env:
            return False
        if key == 'fields':
            return bool(self.env['ir.model.fields'].sudo()._get(model_name, line.get('field')))
        if key == 'buttons' and line.get('button_type') == 'action':
            action = line.get('action') or {}
            return action.get('type', 'ir.actions.act_window') in self.env and bool(
                self._om_find(action, action.get('type') or 'ir.actions.act_window'))
        return True

    @api.model
    def _om_view_names(self, model_name):
        """ {tag: names} of the named nodes of every view of a model, inherited and inactive ones included. """
        names = {}
        views = self.env['ir.ui.view'].sudo().with_context(active_test=False).search([('model', '=', model_name)])
        for view in views:
            try:
                arch = etree.fromstring(view.arch_db or '<data/>')
            except etree.XMLSyntaxError:
                continue
            for node in arch.iter(tag=etree.Element):
                if node.get('name'):
                    names.setdefault(node.tag, set()).add(node.get('name'))
                # Odoo 16 names an app of the Settings by its data-key
                if app := settings_app(node):
                    names.setdefault('app', set()).add(app)
        return names

    def _om_health_unmatched(self):
        """ The button and element rules no view or method answers to any more. """
        issues = []
        names_of = {}

        def names(model_name):
            if model_name not in names_of:
                names_of[model_name] = self._om_view_names(model_name)
            return names_of[model_name]

        for line in self.button_ids:
            model_name = line.model_id.model
            if line.button_type != 'object' or model_name not in self.env:
                continue
            # a method without a button still answers a call: the rule blocks it
            if line.button_name not in names(model_name).get('button', set()) | names(model_name).get('a', set()) \
                    and not callable(getattr(self.env[model_name], line.button_name, None)):
                issues.append(self._om_health_line_issue('unmatched', line, _("Buttons"),
                                                         _("no button nor method of this name")))
        for line in self.element_ids:
            tag = NODE_TAGS.get(line.element_type)
            if not tag or not line.model_id.model:
                continue
            if (line.element_name or '') not in names(line.model_id.model).get(tag, ()):
                issues.append(self._om_health_line_issue('unmatched', line, _("View Elements"),
                                                         _("no view has it any more")))
        return issues

    def _om_health_broken(self):
        """ The record filters and the conditions that no longer evaluate. """
        issues = []
        checks = [
            (self.model_ids, '_check_domain', _("Models")),
            (self.field_ids, '_check_condition', _("Fields")),
            (self.button_ids, '_check_condition', _("Buttons")),
            (self.element_ids, '_check_condition', _("View Elements")),
        ]
        for lines, method, rule in checks:
            for line in lines:
                if line.model_id.model not in self.env:
                    continue
                try:
                    getattr(line, method)()
                except ValidationError as error:
                    issues.append(self._om_health_line_issue('broken', line, rule, str(error.args[0])))
        return issues

    def _om_health_missing(self):
        """ The allowed records and action buttons whose record was deleted. """
        issues = []
        for line in self.allowed_ids.filtered(lambda line: not line.per_user):
            if line.res_model not in self.env or not self.env[line.res_model].sudo().browse(line.res_id).exists():
                issues.append(self._om_health_line_issue(
                    'missing', line, _("Allowed Records"),
                    _("%(kind)s #%(id)s was deleted", id=line.res_id,
                      kind=dict(line._fields['kind']._description_selection(self.env)).get(line.kind))))
        for line in self.button_ids.filtered(lambda line: line.button_type == 'action'):
            if not (line.button_name or '').isdigit() or not self.env['ir.actions.actions'].sudo().browse(
                    int(line.button_name)).exists():
                issues.append(self._om_health_line_issue('missing', line, _("Buttons"), _("its action was deleted")))
        return issues

    @api.model
    def _om_health_line_name(self, line):
        """ The rule as the user reads it: its data, then what it names there. """
        if line._name == 'om.access.allowed':
            return line._om_history_label()
        what = {
            'om.access.profile.field': lambda: line.field_id.field_description,
            'om.access.profile.button': lambda: line.button_label or line.button_name,
            'om.access.profile.element': lambda: line.element_label or line.element_name,
        }.get(line._name, lambda: '')()
        return ' / '.join(filter(None, [line.model_id.name, what]))

    @api.model
    def _om_health_line_issue(self, kind, line, rule, details):
        return {
            'kind': kind, 'rule': rule, 'name': self._om_health_line_name(line), 'details': details,
            'res_model': line._name, 'res_id': line.id,
        }
