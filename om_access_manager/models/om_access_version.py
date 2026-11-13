# Versions of an access profile: the whole profile, as its export describes it,
# saved once per transaction that changed it. Two versions compare line by
# line, and a version restores onto its profile.
import json

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

PENDING = 'om_access_manager.versions'
KEEP = 200  # versions kept per profile, the oldest are dropped

# the lists of an export: their profile field, the model of their lines, and
# the values that tell a line from the others
LISTS = {
    'groups': ('group_ids', None, None),
    'granted_groups': ('granted_group_ids', None, None),
    'hidden_menus': ('hidden_menu_ids', None, None),
    'hidden_reports': ('hidden_report_ids', None, None),
    'hidden_server_actions': ('hidden_action_ids', None, None),
    'hidden_window_actions': ('hidden_window_action_ids', None, None),
    'users': ('user_ids', None, None),
    'models': ('model_ids', 'om.access.profile.model', ('model',)),
    'menu_rules': ('menu_rule_ids', 'om.access.profile.menu', ('menu',)),
    'fields': ('field_ids', 'om.access.profile.field', ('model', 'field')),
    'buttons': ('button_ids', 'om.access.profile.button',
                ('model', 'button_type', 'button_name', 'action', 'view_type', 'button_id')),
    'elements': ('element_ids', 'om.access.profile.element', ('model', 'element_type', 'element_name')),
    'allowed': ('allowed_ids', 'om.access.allowed', ('kind', 'per_user', 'record')),
    'login_slots': ('login_slot_ids', 'om.access.login.slot', ('dayofweek', 'hour_from', 'hour_to')),
}
SINGLE_REFS = {'home_action': 'home_action_id'}


class OmAccessProfileVersion(models.Model):
    _name = 'om.access.profile.version'
    _description = 'Version of an Access Profile'
    _order = 'profile_id, number desc'
    _rec_name = 'number'

    profile_id = fields.Many2one('om.access.profile', string='Profile', required=True, readonly=True,
                                 index=True, ondelete='cascade')
    number = fields.Integer(string='Version', required=True, readonly=True)
    data = fields.Text(required=True, readonly=True)
    summary = fields.Char(readonly=True)
    restored_from_id = fields.Many2one('om.access.profile.version', string='Restored From', readonly=True,
                                       ondelete='set null')
    changes = fields.Html(string='Changes in this Version', compute='_compute_changes', sanitize=False)
    changes_since = fields.Html(string='Changed Since', compute='_compute_changes_since', sanitize=False)
    is_current = fields.Boolean(compute='_compute_changes_since')

    _number_unique = models.Constraint('UNIQUE(profile_id, number)', "A profile has each version once.")

    @api.depends('number', 'profile_id')
    def _compute_display_name(self):
        for version in self:
            version.display_name = _("Version %(number)s", number=version.number)

    def _previous(self):
        self.ensure_one()
        return self.search([('profile_id', '=', self.profile_id.id), ('number', '<', self.number)],
                           order='number desc', limit=1)

    @api.depends('data')
    def _compute_changes(self):
        Profile = self.env['om.access.profile']
        for version in self:
            previous = version._previous()
            if not previous:
                version.changes = Markup('<p class="text-muted">%s</p>') % _("The first version of the profile.")
                continue
            version.changes = Profile._om_diff_html(json.loads(previous.data), json.loads(version.data))

    @api.depends('data', 'profile_id')
    def _compute_changes_since(self):
        for version in self:
            current = version.profile_id._om_version_data()
            version.is_current = current == json.loads(version.data)
            version.changes_since = Markup('<p class="text-muted">%s</p>') % _(
                "The profile is as this version left it.") if version.is_current else \
                self.env['om.access.profile']._om_diff_html(json.loads(version.data), current)

    def action_restore(self):
        """ Make the profile what this version was. Its users stay as they are. """
        self.ensure_one()
        if self.is_current:
            raise UserError(_("The profile is already as this version left it."))
        profile = self.profile_id
        data = json.loads(self.data)
        notes = profile.with_context(om_access_no_history=True)._om_apply_export(data, with_users=False)
        body = Markup('<p>%s</p>') % _(
            "Restored %(version)s, of %(date)s.", version=self.display_name,
            date=fields.Datetime.to_string(fields.Datetime.context_timestamp(self, self.create_date)))
        if notes:
            body += profile._om_notes_html(notes)
        profile.message_post(body=body, subtype_xmlid='mail.mt_note')
        profile._om_version_later(restored_from=self)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'om.access.profile',
            'res_id': profile.id,
            'view_mode': 'form',
            'target': 'main',
        }


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    version_ids = fields.One2many('om.access.profile.version', 'profile_id', string='Versions')
    version_count = fields.Integer(compute='_compute_version_count')

    def _compute_version_count(self):
        counts = dict(self.env['om.access.profile.version']._read_group(
            [('profile_id', 'in', self.ids)], ['profile_id'], ['__count']))
        for profile in self:
            profile.version_count = counts.get(profile, 0)

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        profiles._om_version_later()
        return profiles

    def write(self, vals):
        result = super().write(vals)
        # a write that changes nothing an export carries makes no version
        self._om_version_later()
        return result

    def action_open_versions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Versions of %s", self.name),
            'res_model': 'om.access.profile.version',
            'view_mode': 'list,form',
            'domain': [('profile_id', '=', self.id)],
            'context': {'create': False},
        }

    #
    # saving versions
    #

    def _om_version_later(self, restored_from=None):
        """ Save a version of these profiles when the transaction is about to commit. """
        if not self:
            return
        data = self.env.cr.precommit.data
        pending = data.get(PENDING)
        if pending is None:
            pending = data[PENDING] = {}
            env = self.env

            @self.env.cr.precommit.add
            def save_versions():
                env['om.access.profile']._om_save_versions(data.pop(PENDING, {}))

        for profile in self:
            entry = pending.setdefault(profile.id, {'uid': self.env.uid})
            if restored_from:
                entry['restored_from'] = restored_from.id

    @api.model
    def _om_save_versions(self, pending):
        Version = self.env['om.access.profile.version'].sudo()
        for profile_id, entry in pending.items():
            profile = self.sudo().with_context(active_test=False).browse(profile_id).exists()
            if not profile:
                continue
            data = profile._om_version_data()
            last = Version.search([('profile_id', '=', profile.id)], order='number desc', limit=1)
            if last and json.loads(last.data) == data:
                continue
            summary = profile._om_diff_summary(json.loads(last.data), data) if last else _("First version")
            Version.with_user(entry['uid']).sudo().create({
                'profile_id': profile.id,
                'number': (last.number or 0) + 1,
                'data': json.dumps(data, sort_keys=True),
                'summary': summary,
                'restored_from_id': entry.get('restored_from'),
            })
            old = Version.search([('profile_id', '=', profile.id)], order='number desc', offset=KEEP)
            old.unlink()

    def _om_version_data(self):
        """ The profile as a version keeps it: its export with its users, in
        English so that a change of language is no change. """
        self.ensure_one()
        exported = self.sudo().with_context(lang='en_US', active_test=False)._om_export_profile(with_users=True)
        # what a version stores, read back the same way to compare
        return json.loads(json.dumps(exported, sort_keys=True, default=str))

    @api.model
    def _om_version_missing(self):
        """ Give a first version to the profiles that have none (on install and upgrade). """
        profiles = self.sudo().with_context(active_test=False).search([('version_ids', '=', False)])
        self._om_save_versions({profile.id: {'uid': self.env.uid} for profile in profiles})

    #
    # comparing two versions
    #

    @api.model
    def _om_ref_label(self, ref):
        if not ref:
            return ''
        if isinstance(ref, dict):
            return ref.get('path') or ref.get('name') or ref.get('xmlid') or ''
        return str(ref)

    @api.model
    def _om_value_label(self, model_name, field_name, value):
        """ A value as the user reads it. """
        if isinstance(value, dict):
            return self._om_ref_label(value)
        if value is False or value is None or value == '':
            return _("(empty)") if not isinstance(value, bool) else _("No")
        if value is True:
            return _("Yes")
        field = self.env[model_name]._fields.get(field_name) if model_name else None
        if field is not None and field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        if field is not None and field.type == 'float' and field_name.startswith('hour_'):
            return '%02d:%02d' % (int(value), round(value % 1 * 60))
        return str(value)

    @api.model
    def _om_field_label(self, model_name, field_name):
        field = self.env[model_name]._fields.get(field_name)
        return field._description_string(self.env) if field is not None else field_name

    @api.model
    def _om_line_label(self, key, line):
        """ What tells a line apart, as the user reads it. """
        if key == 'models':
            return self.env['ir.model']._get(line.get('model')).name or line.get('model')
        if key == 'menu_rules':
            return self._om_ref_label(line.get('menu'))
        if key == 'fields':
            field = self.env['ir.model.fields']._get(line.get('model'), line.get('field')) \
                if line.get('model') in self.env else None
            model = self.env['ir.model']._get(line.get('model')).name or line.get('model')
            return '%s / %s' % (model, field.field_description if field else line.get('field'))
        if key == 'buttons':
            model = self.env['ir.model']._get(line.get('model')).name or line.get('model')
            label = line.get('button_label') or self._om_ref_label(line.get('action')) or line.get('button_name')
            return '%s / %s' % (model, label)
        if key == 'elements':
            model = self.env['ir.model']._get(line.get('model')).name or line.get('model')
            return '%s / %s' % (model, line.get('element_label') or line.get('element_name'))
        if key == 'allowed':
            kind = self._om_value_label('om.access.allowed', 'kind', line.get('kind'))
            what = _("their own") if line.get('per_user') else self._om_ref_label(line.get('record'))
            return '%s: %s' % (kind, what)
        if key == 'login_slots':
            Slot = 'om.access.login.slot'
            return '%s %s - %s' % (
                self._om_value_label(Slot, 'dayofweek', line.get('dayofweek')),
                self._om_value_label(Slot, 'hour_from', line.get('hour_from')),
                self._om_value_label(Slot, 'hour_to', line.get('hour_to')))
        return self._om_ref_label(line)

    @api.model
    def _om_diff(self, old, new):
        """ The differences from ``old`` to ``new``, two exports of a profile:
        [(kind, what, label, details)], kind being 'added', 'removed' or 'changed'. """
        Profile = 'om.access.profile'
        changes = []
        # the values of the profile itself
        for key in sorted(set(old) | set(new)):
            if key in LISTS or key == 'name':
                continue
            before, after = old.get(key), new.get(key)
            if before == after or (not before and not after):
                continue
            field_name = SINGLE_REFS.get(key, key)
            changes.append(('changed', self._om_field_label(Profile, field_name), '', [(
                '', self._om_value_label(Profile, field_name, before),
                self._om_value_label(Profile, field_name, after))]))
        # its lists
        for key, (field_name, line_model, identity) in LISTS.items():
            what = self._om_field_label(Profile, field_name)
            before, after = old.get(key) or [], new.get(key) or []
            if line_model is None:
                labels_before = {self._om_ref_label(ref) for ref in before}
                labels_after = {self._om_ref_label(ref) for ref in after}
                changes += [('added', what, label, []) for label in sorted(labels_after - labels_before)]
                changes += [('removed', what, label, []) for label in sorted(labels_before - labels_after)]
                continue

            def ident(line):
                return json.dumps([line.get(name) for name in identity], sort_keys=True)

            lines_before = {ident(line): line for line in before}
            lines_after = {ident(line): line for line in after}
            for line_id, line in lines_after.items():
                if line_id not in lines_before:
                    changes.append(('added', what, self._om_line_label(key, line), []))
                    continue
                previous = lines_before[line_id]
                details = [
                    (self._om_field_label(line_model, name),
                     self._om_value_label(line_model, name, previous.get(name)),
                     self._om_value_label(line_model, name, line.get(name)))
                    for name in sorted(set(line) | set(previous))
                    if name not in identity and previous.get(name) != line.get(name)
                    and (previous.get(name) or line.get(name))
                ]
                if details:
                    changes.append(('changed', what, self._om_line_label(key, line), details))
            for line_id, line in lines_before.items():
                if line_id not in lines_after:
                    changes.append(('removed', what, self._om_line_label(key, line), []))
        if old.get('name') != new.get('name'):
            changes.insert(0, ('changed', self._om_field_label(Profile, 'name'), '', [
                ('', old.get('name') or '', new.get('name') or '')]))
        return changes

    @api.model
    def _om_diff_html(self, old, new):
        changes = self._om_diff(old, new)
        if not changes:
            return Markup('<p class="text-muted">%s</p>') % _("No difference.")
        signs = {
            'added': Markup('<span class="text-success fw-bold">+</span>'),
            'removed': Markup('<span class="text-danger fw-bold">&#8722;</span>'),
            'changed': Markup('<span class="text-warning fw-bold">&#126;</span>'),
        }
        items = []
        for kind, what, label, details in changes:
            text = Markup('%s <b>%s</b>') % (signs[kind], what)
            if label:
                text += Markup(': %s') % label
            if details:
                text += Markup('<ul>%s</ul>') % Markup('').join(
                    Markup('<li>%s%s &#8594; %s</li>') % (
                        Markup('%s: ') % name if name else '', escape(before), escape(after))
                    for name, before, after in details)
            items.append(Markup('<li>%s</li>') % text)
        return Markup('<ul class="list-unstyled">%s</ul>') % Markup('').join(items)

    @api.model
    def _om_diff_summary(self, old, new):
        changes = self._om_diff(old, new)
        if not changes:
            return _("No change")
        words = {'added': _("Added"), 'removed': _("Removed"), 'changed': _("Changed")}
        parts = ['%s %s%s' % (words[kind], what, ': %s' % label if label else '')
                 for kind, what, label, _details in changes[:2]]
        if len(changes) > 2:
            parts.append(_("and %s more", len(changes) - 2))
        return '; '.join(parts)
