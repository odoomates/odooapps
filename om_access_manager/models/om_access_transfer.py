# Export and import of access profiles between databases. Records travel by
# technical name, external id or name, never by database id; what the target
# lacks is skipped and reported on the profile.
import json

from markupsafe import Markup, escape

from odoo import _, api, models
from odoo.exceptions import UserError

FORMAT = 'om_access_manager'
VERSION = 1

# the plain fields of a profile and of its lines, carried as they are
PROFILE_FIELDS = (
    'strictness', 'apply_to_admin', 'for_new_users', 'global_readonly', 'hide_chatter_all',
    'block_export', 'block_import', 'block_archive', 'block_duplicate', 'hide_activities',
    'hide_settings_menu', 'lock_statusbar', 'block_rpc', 'block_developer_mode', 'block_login',
    'hide_print_all', 'hide_action_menu_all', 'hide_send_message_all', 'hide_followers_all',
    'hide_attachments_all', 'hide_costs', 'hide_sale_prices', 'note', 'block_custom_filter',
    'block_custom_group', 'block_favorites', 'block_properties', 'block_apps',
)
MODEL_LINE_FIELDS = (
    'perm_read', 'perm_write', 'perm_create', 'perm_unlink', 'domain', 'domain_read',
    'domain_write', 'domain_create', 'domain_unlink', 'hide_chatter', 'hide_export', 'hide_import',
    'hide_archive', 'hide_duplicate', 'hide_print', 'hide_action_menu', 'hide_send_message',
    'hide_followers', 'hide_attachments',
)
MENU_LINE_FIELDS = MODEL_LINE_FIELDS[:4] + MODEL_LINE_FIELDS[9:] + ('records', 'edit_draft_only', 'include_shared')
FIELD_LINE_FIELDS = ('mode', 'no_open', 'no_create', 'no_export', 'field_domain', 'condition')
BUTTON_LINE_FIELDS = ('view_type', 'button_type', 'button_id', 'button_label', 'mode', 'condition')
ELEMENT_LINE_FIELDS = ('element_type', 'element_name', 'element_label', 'condition')


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    #
    # references that survive a change of database
    #

    @api.model
    def _om_ref(self, record):
        """ The external id of ``record``, else what finds it by name. """
        if not record:
            return None
        record = record.sudo()
        # the name always travels with the external id: some external ids hold
        # a company id (account.1_sale) that differs from a database to another
        ref = {'name': record.display_name}
        xmlid = record.get_external_id().get(record.id)
        if xmlid and not xmlid.startswith('__'):
            ref['xmlid'] = xmlid
        if record._name == 'ir.ui.menu':
            ref['path'] = record.complete_name
        return ref

    @api.model
    def _om_find(self, ref, model_name):
        """ The record ``ref`` designates on this database, or an empty recordset. """
        Model = self.env[model_name].sudo()
        if not ref:
            return Model
        if ref.get('xmlid'):
            record = self.env.ref(ref['xmlid'], raise_if_not_found=False)
            if record and record._name == model_name:
                return record.sudo()
        if ref.get('path') and model_name == 'ir.ui.menu':
            menu = Model
            for part in ref['path'].split('/'):
                menu = Model.search([('name', '=', part.strip()),
                                     ('parent_id', '=', menu.id or False)], limit=1)
                if not menu:
                    return Model
            return menu
        if ref.get('name') and model_name != 'ir.ui.menu':
            # the displayed name first ("WH/Stock" for a location), then the name
            found = Model.browse([
                record_id for record_id, _name in Model.name_search(ref['name'], operator='=', limit=2)])
            if len(found) != 1 and 'name' in Model._fields:
                found = Model.search([('name', '=', ref['name'])], limit=2)
            return found if len(found) == 1 else Model
        return Model

    #
    # export
    #

    def _om_export_profile(self, with_users=False):
        self.ensure_one()
        profile = self.sudo()
        data = {'name': profile.name}
        data.update({name: profile[name] or False for name in PROFILE_FIELDS})
        data['home_action'] = self._om_ref(profile.home_action_id)
        data['groups'] = [self._om_ref(group) for group in profile.group_ids]
        data['granted_groups'] = [self._om_ref(group) for group in profile.granted_group_ids]
        data['hidden_menus'] = [self._om_ref(menu) for menu in profile.hidden_menu_ids]
        data['hidden_reports'] = [self._om_ref(report) for report in profile.hidden_report_ids]
        data['hidden_server_actions'] = [self._om_ref(action) for action in profile.hidden_action_ids]
        data['hidden_window_actions'] = [self._om_ref(action) for action in profile.hidden_window_action_ids]
        data['models'] = [
            dict({name: line[name] or False for name in MODEL_LINE_FIELDS}, model=line.model_id.model)
            for line in profile.model_ids
        ]
        data['menu_rules'] = [
            dict({name: line[name] or False for name in MENU_LINE_FIELDS}, menu=self._om_ref(line.menu_id))
            for line in profile.menu_rule_ids
        ]
        data['fields'] = [
            dict({name: line[name] or False for name in FIELD_LINE_FIELDS},
                 model=line.model_id.model, field=line.field_id.name)
            for line in profile.field_ids
        ]
        buttons = []
        for line in profile.button_ids:
            button = dict({name: line[name] or False for name in BUTTON_LINE_FIELDS}, model=line.model_id.model)
            if line.button_type == 'action' and (line.button_name or '').isdigit():
                # an action button names its action by id: carry the action itself
                action = self.env['ir.actions.actions'].sudo().browse(int(line.button_name)).exists()
                if action:
                    action = self.env[action.type].sudo().browse(action.id)
                button['action'] = dict(self._om_ref(action) or {}, type=action.type) if action else None
            else:
                button['button_name'] = line.button_name
            buttons.append(button)
        data['buttons'] = buttons
        data['elements'] = [
            dict({name: line[name] or False for name in ELEMENT_LINE_FIELDS}, model=line.model_id.model)
            for line in profile.element_ids
        ]
        allowed = []
        for line in profile.allowed_ids:
            item = {'kind': line.kind, 'per_user': line.per_user}
            if not line.per_user and line.res_model in self.env:
                item['record'] = self._om_ref(self.env[line.res_model].sudo().browse(line.res_id).exists())
            allowed.append(item)
        data['allowed'] = allowed
        if with_users:
            data['users'] = profile.user_ids.mapped('login')
        return data

    def _om_export(self, with_users=False):
        return json.dumps({
            'format': FORMAT,
            'version': VERSION,
            'profiles': [profile._om_export_profile(with_users) for profile in self],
        }, indent=2, default=str)

    def action_export_profiles(self):
        # the logins travel too; assigning them is a choice made at import
        content = self._om_export(with_users=True)
        name = 'access_profiles.json' if len(self) != 1 else '%s.json' % self.name
        attachment = self.env['ir.attachment'].create({
            'name': name,
            'raw': content.encode(),
            'mimetype': 'application/json',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'download',
        }

    #
    # import
    #

    @api.model
    def _om_import(self, content, replace=False, with_users=False):
        """ Create the profiles of an export; return them. """
        try:
            payload = json.loads(content)
        except (ValueError, TypeError) as error:
            raise UserError(_("This file is not an export of access profiles.")) from error
        if not isinstance(payload, dict) or payload.get('format') != FORMAT:
            raise UserError(_("This file is not an export of access profiles."))
        if payload.get('version', 0) > VERSION:
            raise UserError(_("This file comes from a newer version of the module: upgrade it first."))
        profiles = self.browse()
        for data in payload.get('profiles', []):
            profiles |= self._om_import_profile(data, replace, with_users)
        return profiles

    @api.model
    def _om_import_profile(self, data, replace, with_users):
        notes = []
        name = data.get('name') or _("Imported Profile")
        existing = self.with_context(active_test=False).search([('name', '=', name)], limit=1)
        if existing and replace:
            existing.write({
                'model_ids': [(5,)], 'menu_rule_ids': [(5,)], 'field_ids': [(5,)], 'button_ids': [(5,)], 'element_ids': [(5,)],
                'allowed_ids': [(5,)], 'group_ids': [(5,)], 'granted_group_ids': [(5,)], 'hidden_menu_ids': [(5,)], 'hidden_report_ids': [(5,)],
                'hidden_action_ids': [(5,)], 'hidden_window_action_ids': [(5,)],
            })
            profile = existing
        else:
            profile = self.create({'name': _("%s (imported)", name) if existing else name})

        values = {key: data[key] for key in PROFILE_FIELDS if key in data and key in self._fields}
        home = self._om_find(data.get('home_action'), 'ir.actions.act_window')
        values['home_action_id'] = home.id or False
        if data.get('home_action') and not home:
            notes.append(_("Home page: not found"))

        def records(refs, model_name, label):
            found = self.env[model_name].sudo()
            for ref in refs or ():
                record = self._om_find(ref, model_name)
                if record:
                    found |= record
                else:
                    notes.append(_("%(what)s not found: %(ref)s", what=label,
                                   ref=ref.get('xmlid') or ref.get('path') or ref.get('name')))
            return found

        values['group_ids'] = [(6, 0, records(data.get('groups'), 'res.groups', _("Group")).ids)]
        values['granted_group_ids'] = [(6, 0, records(data.get('granted_groups'), 'res.groups', _("Group")).ids)]
        values['hidden_menu_ids'] = [(6, 0, records(data.get('hidden_menus'), 'ir.ui.menu', _("Menu")).ids)]
        values['hidden_report_ids'] = [(6, 0, records(
            data.get('hidden_reports'), 'ir.actions.report', _("Report")).ids)]
        values['hidden_action_ids'] = [(6, 0, records(
            data.get('hidden_server_actions'), 'ir.actions.server', _("Action")).ids)]
        values['hidden_window_action_ids'] = [(6, 0, records(
            data.get('hidden_window_actions'), 'ir.actions.act_window', _("Action")).ids)]

        IrModel = self.env['ir.model'].sudo()
        model_lines = []
        for line in data.get('models', []):
            ir_model = IrModel._get(line.get('model')) if line.get('model') in self.env else IrModel
            if not ir_model:
                notes.append(_("Data not installed: %s", line.get('model')))
                continue
            model_lines.append((0, 0, dict(
                {key: line[key] for key in MODEL_LINE_FIELDS if key in line}, model_id=ir_model.id)))
        values['model_ids'] = model_lines

        menu_lines = []
        for line in data.get('menu_rules', []):
            menu = records([line['menu']] if line.get('menu') else [], 'ir.ui.menu', _("Menu"))
            if menu:
                menu_lines.append((0, 0, dict(
                    {key: line[key] for key in MENU_LINE_FIELDS if key in line}, menu_id=menu.id)))
        values['menu_rule_ids'] = menu_lines

        field_lines = []
        for line in data.get('fields', []):
            field = self.env['ir.model.fields'].sudo()._get(line.get('model'), line.get('field')) \
                if line.get('model') in self.env else None
            if not field:
                notes.append(_("Field not installed: %(model)s / %(field)s",
                               model=line.get('model'), field=line.get('field')))
                continue
            field_lines.append((0, 0, dict(
                {key: line[key] for key in FIELD_LINE_FIELDS if key in line},
                model_id=field.model_id.id, field_id=field.id)))
        values['field_ids'] = field_lines

        button_lines = []
        for line in data.get('buttons', []):
            if line.get('model') not in self.env:
                notes.append(_("Data not installed: %s", line.get('model')))
                continue
            button_name = line.get('button_name')
            if line.get('button_type') == 'action':
                action_ref = line.get('action') or {}
                action = self._om_find(action_ref, action_ref.get('type') or 'ir.actions.act_window') \
                    if action_ref.get('type', 'ir.actions.act_window') in self.env else None
                if not action:
                    notes.append(_("Button action not found: %s",
                                   action_ref.get('xmlid') or action_ref.get('name')))
                    continue
                button_name = str(action.id)
            button_lines.append((0, 0, dict(
                {key: line[key] for key in BUTTON_LINE_FIELDS if key in line},
                model_id=IrModel._get(line['model']).id, button_name=button_name)))
        values['button_ids'] = button_lines

        element_lines = []
        for line in data.get('elements', []):
            if line.get('model') not in self.env:
                notes.append(_("Data not installed: %s", line.get('model')))
                continue
            element_lines.append((0, 0, dict(
                {key: line[key] for key in ELEMENT_LINE_FIELDS if key in line},
                model_id=IrModel._get(line['model']).id)))
        values['element_ids'] = element_lines

        allowed_lines = []
        kinds = dict(self.env['om.access.allowed']._selection_kinds())
        Allowed = self.env['om.access.allowed']
        for line in data.get('allowed', []):
            if line.get('kind') not in kinds:
                notes.append(_("Allowed records of an app not installed: %s", line.get('kind')))
                continue
            if line.get('per_user'):
                allowed_lines.append((0, 0, {'kind': line['kind'], 'per_user': True}))
                continue
            model_name = Allowed.new({'kind': line['kind']}).res_model
            record = self._om_find(line.get('record'), model_name)
            if not record:
                notes.append(_("Allowed record not found: %s",
                               (line.get('record') or {}).get('xmlid') or (line.get('record') or {}).get('name')))
                continue
            allowed_lines.append((0, 0, {'kind': line['kind'], 'res_id': record.id}))
        values['allowed_ids'] = allowed_lines

        if with_users and data.get('users'):
            users = self.env['res.users'].sudo().search([('login', 'in', data['users'])])
            values['user_ids'] = [(6, 0, users.ids)]
            for login in set(data['users']) - set(users.mapped('login')):
                notes.append(_("User not found: %s", login))

        profile.write(values)
        body = Markup('<p>%s</p>') % _("Imported from a file.")
        if notes:
            body += Markup('<p>%s</p><ul>%s</ul>') % (
                _("Skipped, not found on this database:"),
                Markup('').join(Markup('<li>%s</li>') % escape(note) for note in notes))
        profile.message_post(body=body, subtype_xmlid='mail.mt_note')
        return profile
