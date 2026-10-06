# The Menus & Apps tab: the menu tree, and the panel of the clicked menu where
# every setting of its data is made. The panel writes the ordinary lines of the
# profile (model, menu, field, button, element lines, hidden reports and
# actions, allowed records), so the other tabs show the same rules.
import logging

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

from .om_access_allowed import ALLOWED_KINDS
from .om_access_profile import MODEL_FLAGS, PERM_FIELDS, UNGRANTABLE_GROUPS
from .om_access_profile_menu import RECORD_CHOICES
from .om_access_profile_model import DOMAIN_FIELDS, DRAFT_DOMAIN

_logger = logging.getLogger(__name__)

# the switches of some data, in the order of the panel
SWITCHES = (
    'hide_chatter', 'hide_send_message', 'hide_followers', 'hide_attachments', 'hide_export',
    'hide_import', 'hide_archive', 'hide_duplicate', 'hide_print', 'hide_action_menu',
)
FIELD_MODES = ('keep', 'readonly', 'hide', 'required')
# the module that brings the data an allowed record kind filters: the kind is
# offered on the app made by that module
KIND_MODULES = {
    'journal': ('account',), 'pos': ('point_of_sale',), 'warehouse': ('stock',),
    'location': ('stock',), 'team': ('sales_team', 'sale', 'crm'), 'dashboard': ('spreadsheet_dashboard',),
}
ACTION_TYPES = {
    'ir.actions.server': 'hidden_action_ids',
    'ir.actions.act_window': 'hidden_window_action_ids',
}
LEVEL_RIGHTS = {
    'full': (True, True, True, True),
    'user': (True, True, True, True),
    'readonly': (True, False, False, False),
    'none': (False, False, False, False),
}


def _om_inherited_values(from_menus):
    """ The values of a model line holding what the menus above give: rights,
    switches and record filters (several filters are joined: a + b is their
    AND once evaluated). """
    rights, by_operation, flags, _menus = from_menus
    values = {**dict(zip(PERM_FIELDS, rights)), **{flag: flag in flags for flag in MODEL_FLAGS}}
    terms = [by_operation.get(operation, ()) for operation in ('read', 'write', 'create', 'unlink')]
    common = [term for term in terms[0] if all(term in other for other in terms[1:])]
    values['domain'] = ' + '.join(common) or False
    for operation, field_name in (('write', 'domain_write'), ('unlink', 'domain_unlink'),
                                  ('read', 'domain_read'), ('create', 'domain_create')):
        extra = [term for term in by_operation.get(operation, ()) if term not in common]
        values[field_name] = ' + '.join(extra) or False
    return values


def _om_write_changes(line, values):
    """ Write only what changes: the history of the profile names those fields. """
    changed = {name: value for name, value in values.items() if (line[name] or False) != (value or False)}
    if changed:
        line.write(changed)


class OmAccessProfile(models.Model):
    _inherit = 'om.access.profile'

    @api.model
    def _om_check_admin(self):
        if not self.env.user.has_group('om_access_manager.group_access_manager'):
            raise AccessError(_("Only the administrators can edit access profiles."))

    #
    # the tree
    #

    @api.model
    def om_menu_tree(self):
        """ Every menu, for the menu tree, with the data it opens. Read with sudo:
        a menu the administrator cannot see may still need hiding. """
        self._om_check_admin()
        menus = self.env['ir.ui.menu'].sudo().search([])
        # the Access Manager app is for the access managers: never hidden or restricted from here
        app = self.env.ref('om_access_manager.om_access_root_menu', raise_if_not_found=False)
        if app:
            menus = menus.filtered(lambda menu: not menu.parent_path.startswith(f'{app.id}/'))
        Wizard = self.env['om.access.app.wizard']
        models_of, roots = {}, {}
        for menu in menus:
            model_name = menu.action and Wizard._menu_model(menu)
            if model_name:
                models_of[menu.id] = model_name
                roots.setdefault(model_name, set()).add(int(menu.parent_path.split('/')[0]))
        labels = {model.model: model.name for model in self.env['ir.model'].sudo().search(
            [('model', 'in', list(roots))])}
        return [{
            'id': menu.id,
            'name': menu.name,
            'parent_id': menu.parent_id.id,
            'model': models_of.get(menu.id) or False,
            'model_label': labels.get(models_of.get(menu.id)) or False,
            'shared': len(roots.get(models_of.get(menu.id), ())) > 1,
        } for menu in menus]

    @api.model
    def om_tree_prints(self):
        """ {model: [report or Action menu entry, ...]} for the data the menus
        open: the rows under each menu of the tree. """
        self._om_check_admin()
        Wizard = self.env['om.access.app.wizard']
        model_names = {
            model_name for menu in self.env['ir.ui.menu'].sudo().search([('action', '!=', False)])
            if (model_name := Wizard._menu_model(menu))
        }
        result = {}
        for report in self.env['ir.actions.report'].sudo().search([('model', 'in', list(model_names))]):
            result.setdefault(report.model, []).append({
                'type': report._name, 'id': report.id, 'label': report.name, 'kind': 'report'})
        for action_model in ACTION_TYPES:
            actions = self.env[action_model].sudo().search([('binding_model_id.model', 'in', list(model_names))])
            for action in actions:
                result.setdefault(action.binding_model_id.model, []).append({
                    'type': action_model, 'id': action.id, 'label': action.name, 'kind': 'action'})
        for entries in result.values():
            entries.sort(key=lambda entry: (entry['kind'] != 'report', (entry['label'] or '').lower()))
            # two reports of the same name (a quotation and its variant): say which
            labels = [entry['label'] for entry in entries]
            for entry in entries:
                if labels.count(entry['label']) > 1 and entry['kind'] == 'report':
                    report = self.env['ir.actions.report'].sudo().browse(entry['id'])
                    entry['label'] = f"{entry['label']} ({report.report_name})"
        return result

    def om_toggle_print(self, action_type, action_id, hidden):
        """ Hide or show a report or an Action menu entry, from its row of the tree. """
        self._om_check_admin()
        self.ensure_one()
        self._om_set_print(None, None, {'type': action_type, 'id': action_id, 'hidden': hidden})
        return True

    def om_tree_state(self):
        """ What the profile restricts, for the marks of the tree: the menu
        rules, and per data what is set on it. """
        self._om_check_admin()
        if not self:
            return {'menu_rules': {}, 'models': {}, 'apps': {}, 'hidden_prints': []}
        self.ensure_one()
        profile = self.sudo()
        menu_rules = {
            line.menu_id.id: self._om_rule_values(line) for line in profile.menu_rule_ids
        }
        inherited = profile.menu_rule_ids._om_rights_by_model()
        state = {}

        def entry(model_name):
            return state.setdefault(model_name, {
                'rights': [True] * 4, 'source': False, 'records': 'all',
                'fields': 0, 'buttons': 0, 'elements': 0, 'print': 0, 'switches': 0})

        for model_name, (rights, by_operation, flags, _menus) in inherited.items():
            item = entry(model_name)
            item.update(rights=list(rights), source='menu', records='filter' if by_operation else 'all',
                        switches=len(flags))
        for line in profile.model_ids:
            item = entry(line.model_id.model)
            item.update(rights=[line[name] for name in PERM_FIELDS], source='data',
                        records=self._om_records_choice(line)[0],
                        switches=sum(1 for flag in MODEL_FLAGS if line[flag]))
        for line in profile.field_ids:
            if line.mode != 'keep' or line.no_export:
                entry(line.model_id.model)['fields'] += 1
        for line in profile.button_ids:
            entry(line.model_id.model)['buttons'] += 1
        for line in profile.element_ids:
            entry(line.model_id.model)['elements'] += 1
        for report in profile.hidden_report_ids:
            entry(report.model)['print'] += 1
        for action in profile.hidden_action_ids:
            if action.binding_model_id:
                entry(action.binding_model_id.model)['print'] += 1
        for action in profile.hidden_window_action_ids:
            if action.binding_model_id:
                entry(action.binding_model_id.model)['print'] += 1
        # the apps holding allowed records
        apps = {}
        Menu = self.env['ir.ui.menu'].sudo()
        for root in Menu.search([('parent_id', '=', False)]):
            count = sum(len(kind['records']) + kind['per_user'] for kind in profile._om_app_allowed(root))
            if count:
                apps[root.id] = count
        hidden_prints = [f'{record._name},{record.id}' for record in (
            *profile.hidden_report_ids, *profile.hidden_action_ids, *profile.hidden_window_action_ids)]
        # the apps this profile opens through a granted group
        granted_apps = [root.id for root in Menu.search([('parent_id', '=', False)])
                        if profile.granted_group_ids & self.env['ir.ui.menu'].sudo().search(
                            [('id', 'child_of', root.id)]).group_ids]
        return {'menu_rules': menu_rules, 'models': state, 'apps': apps, 'hidden_prints': hidden_prints,
                'granted_apps': granted_apps}

    def om_app_access(self, user_ids):
        """ Per app (top menu) opened by groups: whether the users of the
        profile can all open it, and what ticking it grants. ``user_ids`` are
        the users on the form, saved or not. """
        self._om_check_admin()
        profile = self.sudo()[:1]
        members = self.env['res.users'].sudo().browse(user_ids).exists()
        if profile:
            members |= profile.group_ids.all_user_ids | profile.assignment_ids.filtered(
                lambda line: line.state == 'active').user_id
        exempt = self.env['om.access.profile']._exempt_user_ids()
        members = members.filtered(lambda user: user.active and not user.share and user.id not in exempt)
        result = {}
        Menu = self.env['ir.ui.menu'].sudo()
        for root in Menu.search([('parent_id', '=', False)]):
            gates = root.group_ids
            if not gates:
                continue
            levels = (profile or self.env['om.access.profile'].sudo().new({}))._om_app_grants(root)
            # the access level of the app itself (Purchase), its lowest group first
            own = next((level for level in levels
                        if gates.privilege_id.filtered(lambda p: p.id == level['privilege_id'])), None)
            if not own:
                continue
            result[root.id] = {
                'gate_ids': gates.ids,
                'grant': {'id': own['groups'][0]['id'],
                          'name': self.env['res.groups'].sudo().browse(own['groups'][0]['id']).display_name},
                'group_ids': [group['id'] for level in levels for group in level['groups']],
                'open': all(user.all_group_ids & gates for user in members),
            }
        return result

    #
    # reading
    #

    @api.model
    def _om_rule_values(self, line):
        values = {name: line[name] for name in PERM_FIELDS + MODEL_FLAGS}
        values.update(records=line.records, edit_draft_only=line.edit_draft_only,
                      include_shared=line.include_shared)
        return values

    @api.model
    def _om_records_choice(self, line):
        """ (choice, edit drafts only) read back from the filters of a model line;
        'custom' for a filter written by hand. """
        presets = self.env['om.access.profile.model']._preset_domains(line.model_id.model)
        domain = (line.domain or '').strip()
        drafts = (line.domain_write or '').strip() == DRAFT_DOMAIN
        others = any((line[name] or '').strip() for name in DOMAIN_FIELDS[1:]
                     if not (drafts and name in ('domain_write', 'domain_unlink')))
        if others:
            return 'custom', drafts
        if not domain:
            return 'all', drafts
        for key, (field_name, preset) in presets.items():
            if field_name == 'domain' and preset == domain:
                return key, drafts
        return 'custom', drafts

    @api.model
    def _om_record_choices(self, model_name):
        presets = self.env['om.access.profile.model']._preset_domains(model_name)
        labels = dict(RECORD_CHOICES)
        return [('all', labels['all'])] + [
            (key, labels[key]) for key, _label in RECORD_CHOICES[1:] if key in presets]

    @api.model
    def _om_view_archs(self, menu, model_name):
        """ [(view type, arch)] of the views the menu opens: the action's own,
        else the default ones. """
        action = menu.sudo().action
        own = {}
        if action and action._name == 'ir.actions.act_window':
            own = {view_type: view_id for view_id, view_type in action.views if view_id}
        model = self.env[model_name].sudo()
        archs = []
        for view_type in ('list', 'form', 'kanban', 'search'):
            try:
                arch = model.get_view(own.get(view_type), view_type=view_type)['arch']
            except Exception:  # noqa: BLE001 - the model may have no such view
                _logger.debug("no %s view for %s", view_type, model_name, exc_info=True)
                continue
            archs.append((view_type, etree.fromstring(arch)))
        return archs

    @staticmethod
    def _om_top_level(node):
        """ Not inside the nested view of an x2many. """
        return not any(ancestor.tag == 'field' for ancestor in node.iterancestors())

    def _om_panel_fields(self, archs, model_name):
        model = self.env[model_name]
        lines = {line.field_id.name: line for line in self.field_ids if line.model_id.model == model_name}
        found = {}
        for view_type, root in archs:
            if view_type == 'search':
                continue
            for node in root.iter('field'):
                name = node.get('name')
                field = model._fields.get(name)
                if (field is None or name in found or not self._om_top_level(node)
                        or node.get('invisible') in ('1', 'True') or node.get('column_invisible') in ('1', 'True')):
                    continue
                found[name] = {
                    'name': name,
                    'label': node.get('string') or field._description_string(self.env),
                    'type': field.type,
                    'mode': lines[name].mode if name in lines else 'keep',
                    'condition': lines[name].condition or '' if name in lines else '',
                    'no_export': bool(name in lines and lines[name].no_export),
                }
        # the rules on fields of other screens of the data
        for name, line in lines.items():
            if name not in found and name in model._fields:
                found[name] = {'name': name, 'label': line.field_id.field_description, 'type': model._fields[name].type,
                               'mode': line.mode, 'condition': line.condition or '', 'no_export': line.no_export}
        return list(found.values())

    def _om_panel_buttons(self, archs, model_name):
        Scan = self.env['om.access.scan.buttons']
        lines = {}
        for line in self.button_ids.filtered(lambda line: line.model_id.model == model_name):
            lines.setdefault((line.button_type, line.button_name), line)
        found = {}
        for view_type, root in archs:
            for node in root.xpath('//button[@name and not(@special)]'):
                button_type = node.get('type') or 'object'
                key = (button_type, node.get('name'))
                if button_type not in ('object', 'action') or key in found or not self._om_top_level(node):
                    continue
                found[key] = Scan._label(node, button_type, key[1])
        for key, line in lines.items():
            found.setdefault(key, line.button_label or line.button_name)
        return [{
            'button_type': button_type, 'button_name': name, 'label': label,
            'mode': lines[(button_type, name)].mode if (button_type, name) in lines else 'visible',
            'condition': lines[(button_type, name)].condition or '' if (button_type, name) in lines else '',
        } for (button_type, name), label in found.items()]

    def _om_panel_elements(self, menu, archs, model_name):
        hidden = {(line.element_type, line.element_name or ''): line
                  for line in self.element_ids if line.model_id.model == model_name}
        found = {}
        for view_type, root in archs:
            if view_type == 'form':
                nodes = [('page', node) for node in root.iter('page')]
            elif view_type == 'search':
                nodes = [('filter', node) for node in root.iter('filter')]
            else:
                continue
            for element_type, node in nodes:
                name = node.get('name') or ''
                if not name or (element_type, name) in found or not self._om_top_level(node):
                    continue
                label = node.get('string') or name
                if element_type == 'filter' and 'group_by' in (node.get('context') or ''):
                    label = _("%s (group by)", label)
                found[(element_type, name)] = label
        action = menu.sudo().action
        if action and action._name == 'ir.actions.act_window':
            labels = dict(self.env['ir.actions.act_window.view']._fields['view_mode']._description_selection(
                self.env))
            for view_type in (action.view_mode or '').split(','):
                view_type = view_type.strip()
                if view_type and view_type != 'form':
                    found[('view', view_type)] = labels.get(view_type, view_type)
        for (element_type, name), line in hidden.items():
            found.setdefault((element_type, name), line.element_label or name)
        return [{
            'element_type': element_type, 'element_name': name, 'label': label,
            'hidden': (element_type, name) in hidden,
            'condition': hidden[(element_type, name)].condition or '' if (element_type, name) in hidden else '',
        } for (element_type, name), label in found.items()]

    def _om_panel_print(self, model_name):
        reports = self.env['ir.actions.report'].sudo().search([('model', '=', model_name)])
        entries = [{'type': 'ir.actions.report', 'id': report.id, 'label': report.name,
                    'kind': _("Print"), 'hidden': report in self.hidden_report_ids} for report in reports]
        for action_model, field_name in ACTION_TYPES.items():
            for action in self.env[action_model].sudo().search([('binding_model_id.model', '=', model_name)]):
                entries.append({'type': action_model, 'id': action.id, 'label': action.name,
                                'kind': _("Action"), 'hidden': action in self[field_name]})
        return entries

    def _om_also_opened_by(self, menu, model_name):
        Wizard = self.env['om.access.app.wizard']
        menus = self.env['ir.ui.menu'].sudo().search([('action', '!=', False), ('id', '!=', menu.id)])
        return [other.complete_name for other in menus if Wizard._menu_model(other) == model_name]

    def _om_app_allowed(self, menu):
        """ The allowed record kinds that belong to the app of ``menu``. """
        xmlid = menu.sudo().get_external_id().get(menu.id, '')
        module = xmlid.split('.')[0] if xmlid else ''
        kinds = [kind for kind, modules in KIND_MODULES.items()
                 if module in modules and kind in ALLOWED_KINDS and ALLOWED_KINDS[kind][1] in self.env]
        result = []
        for kind in kinds:
            label, model_name, _filters = ALLOWED_KINDS[kind]
            lines = self.allowed_ids.filtered(lambda line: line.kind == kind)
            result.append({
                'kind': kind, 'label': str(label), 'model': model_name,
                'per_user': any(lines.mapped('per_user')),
                'records': [{'line_id': line.id, 'id': line.res_id, 'name': line.display_name}
                            for line in lines if not line.per_user],
            })
        return result

    def _om_app_grants(self, menu):
        """ The groups that open the app of ``menu``, by privilege (Purchase:
        User, Administrator), and which one this profile grants. """
        menus = self.env['ir.ui.menu'].sudo().search([('id', 'child_of', menu.id)])
        gates = menus.group_ids
        privileges = gates.privilege_id
        forbidden = self.env['res.groups']
        for xmlid in UNGRANTABLE_GROUPS:
            forbidden |= self.env.ref(xmlid, raise_if_not_found=False) or self.env['res.groups']
        result = []
        for privilege in privileges.sorted(lambda p: (p.sequence, p.name)):
            groups = self.env['res.groups'].sudo().search([('privilege_id', '=', privilege.id)]).filtered(
                lambda group: not ((group | group.all_implied_ids) & forbidden))
            if not groups:
                continue
            # the lower levels first: a group implying another of the app comes after it
            groups = groups.sorted(lambda group: (len(group.all_implied_ids & groups), group.sequence, group.id))
            granted = groups & self.granted_group_ids
            result.append({
                'privilege_id': privilege.id, 'name': privilege.name,
                'groups': [{'id': group.id, 'name': group.name} for group in groups],
                'granted': granted[:1].id or False,
            })
        return result

    def om_menu_panel(self, menu_id):
        """ Everything the panel shows for one menu of this profile. """
        self._om_check_admin()
        self.ensure_one()
        profile = self.sudo()
        menu = self.env['ir.ui.menu'].sudo().browse(menu_id).exists()
        if not menu:
            raise UserError(_("This menu no longer exists."))
        model_name = menu.action and self.env['om.access.app.wizard']._menu_model(menu)
        rules = {line.menu_id.id: line for line in profile.menu_rule_ids}
        ancestors = [int(part) for part in menu.parent_path.split('/') if part][:-1][::-1]
        inherited = next((rules[menu_id] for menu_id in ancestors if menu_id in rules), None)
        data = {
            'menu': {'id': menu.id, 'name': menu.name, 'path': menu.complete_name,
                     'depth': len(ancestors), 'has_children': bool(menu.child_id)},
            'hidden': bool(set(profile.hidden_menu_ids._ids) & {menu.id, *ancestors}),
            'rule': self._om_rule_values(rules[menu.id]) if menu.id in rules else False,
            'inherited': inherited and dict(self._om_rule_values(inherited),
                                            menu=inherited.menu_id.complete_name),
            'switch_labels': {flag: self.env['om.access.profile.model']._fields[flag].string for flag in SWITCHES},
            'record_labels': dict(RECORD_CHOICES),
            'model': False,
        }
        if not menu.parent_id:
            data['allowed'] = profile._om_app_allowed(menu)
            data['grants'] = profile._om_app_grants(menu)
        if menu.child_id:
            data['level'] = profile._om_current_level(menu, rules.get(menu.id))
        if model_name:
            line = profile.model_ids.filtered(lambda line: line.model_id.model == model_name)[:1]
            from_menus = profile.menu_rule_ids._om_rights_by_model().get(model_name)
            if line:
                records, drafts = self._om_records_choice(line)
                rights = dict({name: line[name] for name in PERM_FIELDS + MODEL_FLAGS},
                              records=records, edit_draft_only=drafts)
                source = 'data'
            elif from_menus:
                rights_tuple, by_operation, flags, _menus = from_menus
                rights = dict(dict(zip(PERM_FIELDS, rights_tuple)), **{flag: flag in flags for flag in MODEL_FLAGS},
                              records='filter' if by_operation else 'all', edit_draft_only=False)
                source = 'menu'
            else:
                rights = dict(dict.fromkeys(PERM_FIELDS, True), **dict.fromkeys(MODEL_FLAGS, False),
                              records='all', edit_draft_only=False)
                source = False
            archs = self._om_view_archs(menu, model_name)
            data.update({
                'model': model_name,
                'model_label': self.env['ir.model']._get(model_name).name,
                'also': self._om_also_opened_by(menu, model_name),
                'rights': rights,
                'source': source,
                'line_id': line.id or False,
                'record_choices': self._om_record_choices(model_name),
                'drafts_possible': 'draft' in self.env['om.access.profile.model']._preset_domains(model_name),
                'fields': profile._om_panel_fields(archs, model_name),
                'buttons': profile._om_panel_buttons(archs, model_name),
                'elements': profile._om_panel_elements(menu, archs, model_name),
                'print': profile._om_panel_print(model_name),
            })
        return data

    def _om_current_level(self, menu, rule):
        """ The access level a menu with children is at, if it matches one. """
        hidden = self.hidden_menu_ids
        if menu in hidden:
            return 'none'
        rights = tuple(rule[name] for name in PERM_FIELDS) if rule else LEVEL_RIGHTS['full']
        config = self._om_config_menus(menu)
        if rights == LEVEL_RIGHTS['readonly'] and not (config & hidden):
            return 'readonly'
        if rights == LEVEL_RIGHTS['full'] and not rule:
            if config and config <= hidden:
                return 'user'
            if not (config & hidden):
                return 'full'
        return False

    #
    # writing
    #

    def om_menu_panel_set(self, menu_id, change):
        """ Apply one change made in the panel; return the panel again. """
        self._om_check_admin()
        self.ensure_one()
        menu = self.env['ir.ui.menu'].sudo().browse(menu_id).exists()
        if not menu:
            raise UserError(_("This menu no longer exists."))
        model_name = menu.action and self.env['om.access.app.wizard']._menu_model(menu)
        kind = change.get('kind')
        handler = getattr(self, f'_om_set_{kind}', None) if kind in (
            'data_rights', 'data_reset', 'data_line', 'grant', 'menu_rights', 'menu_reset', 'level', 'field', 'button',
            'element', 'print', 'allowed', 'hide_menu') else None
        if handler is None:
            raise UserError(_("Unknown change: %s", kind))
        handler(menu, model_name, change)
        return self.om_menu_panel(menu_id)

    def _om_model_line(self, model_name, create=True):
        line = self.model_ids.filtered(lambda line: line.model_id.model == model_name)[:1]
        if not line and create:
            line = self.env['om.access.profile.model'].create({
                'profile_id': self.id, 'model_id': self.env['ir.model']._get(model_name).id})
        return line

    def _om_set_data_rights(self, menu, model_name, change):
        if not model_name:
            raise UserError(_("This menu opens no data."))
        values = {name: bool(change[name]) for name in PERM_FIELDS + MODEL_FLAGS if name in change}
        line = self._om_model_line(model_name, create=False)
        from_menus = self.menu_rule_ids._om_rights_by_model().get(model_name)
        if not line and from_menus:
            # start from what the menus above give, so changing one box keeps the others
            values = {**_om_inherited_values(from_menus), **values}
        records = change.get('records')
        presets = self.env['om.access.profile.model']._preset_domains(model_name)
        if records == 'all':
            values['domain'] = False
        elif records in presets and presets[records][0] == 'domain':
            values['domain'] = presets[records][1]
        if 'edit_draft_only' in change and 'draft' in presets:
            drafts = DRAFT_DOMAIN if change['edit_draft_only'] else False
            values.update(domain_write=drafts, domain_unlink=drafts)
        if line:
            _om_write_changes(line, values)
            self._om_drop_if_empty(line)
        elif from_menus or not (all(values.get(name, True) for name in PERM_FIELDS)
                                and not any(values.get(name) for name in MODEL_FLAGS + DOMAIN_FIELDS)):
            self.env['om.access.profile.model'].create(dict(
                values, profile_id=self.id, model_id=self.env['ir.model']._get(model_name).id))

    def _om_drop_if_empty(self, line):
        """ No line means full access: one back to everything allowed goes. """
        if (line and all(line[name] for name in PERM_FIELDS)
                and not any(line[name] for name in MODEL_FLAGS)
                and not any((line[name] or '').strip() for name in DOMAIN_FIELDS)
                and not self.menu_rule_ids._om_rights_by_model().get(line.model_id.model)):
            line.unlink()

    def _om_set_data_line(self, menu, model_name, change):
        """ A rule on the data, kept even at full access: the filters are about
        to be written in the rule form. """
        if not model_name:
            raise UserError(_("This menu opens no data."))
        if not self._om_model_line(model_name, create=False):
            from_menus = self.menu_rule_ids._om_rights_by_model().get(model_name)
            line = self._om_model_line(model_name)
            if from_menus:
                line.write(_om_inherited_values(from_menus))

    def _om_set_grant(self, menu, model_name, change):
        """ Grant one group of a privilege (Purchase / User), or none of them. """
        privilege = self.env['res.groups.privilege'].sudo().browse(change.get('privilege_id')).exists()
        if not privilege:
            raise UserError(_("Unknown access level."))
        of_privilege = self.env['res.groups'].sudo().search([('privilege_id', '=', privilege.id)])
        granted = self.granted_group_ids - of_privilege
        if change.get('group_id'):
            group = of_privilege.filtered(lambda group: group.id == change['group_id'])
            if not group:
                raise UserError(_("This group does not open this app."))
            granted |= group
        self.granted_group_ids = granted

    def _om_set_data_reset(self, menu, model_name, change):
        self._om_model_line(model_name, create=False).unlink()

    def _om_set_menu_rights(self, menu, model_name, change):
        Rule = self.env['om.access.profile.menu']
        rule = self.menu_rule_ids.filtered(lambda line: line.menu_id == menu)
        values = {name: change[name] for name in PERM_FIELDS + MODEL_FLAGS
                  + ('records', 'edit_draft_only', 'include_shared') if name in change}
        if rule:
            _om_write_changes(rule, values)
        else:
            inherited = self._om_inherited_rule(menu)
            base = self._om_rule_values(inherited) if inherited else {}
            Rule.create(dict(base, **values, profile_id=self.id, menu_id=menu.id))

    def _om_inherited_rule(self, menu):
        rules = {line.menu_id.id: line for line in self.menu_rule_ids}
        ancestors = [int(part) for part in menu.parent_path.split('/') if part][:-1][::-1]
        return next((rules[menu_id] for menu_id in ancestors if menu_id in rules), None)

    def _om_set_menu_reset(self, menu, model_name, change):
        self.menu_rule_ids.filtered(lambda line: line.menu_id == menu).unlink()

    def _om_config_menus(self, menu):
        """ The configuration submenus right under an app. """
        xmlids = menu.child_id.get_external_id()
        return menu.child_id.filtered(
            lambda child: 'config' in xmlids.get(child.id, '').split('.')[-1].lower()
            or (child.name or '').strip().lower() == 'configuration')

    def _om_set_level(self, menu, model_name, change):
        """ An access level on a menu with children: rights for all the data
        below, the configuration hidden for a user, the menu hidden for none. """
        level = change.get('level')
        if level not in LEVEL_RIGHTS:
            raise UserError(_("Unknown access level: %s", level))
        config = self._om_config_menus(menu)
        hidden = self.hidden_menu_ids - config - menu
        if level == 'user':
            hidden |= config
        if level == 'none':
            hidden |= menu
        self.hidden_menu_ids = hidden
        rule = self.menu_rule_ids.filtered(lambda line: line.menu_id == menu)
        if level in ('full', 'user'):
            rule.unlink()
        else:
            self._om_set_menu_rights(menu, model_name, dict(zip(PERM_FIELDS, LEVEL_RIGHTS[level])))

    def _om_set_hide_menu(self, menu, model_name, change):
        if change.get('hidden'):
            self.hidden_menu_ids |= menu
        else:
            self.hidden_menu_ids -= menu

    def _om_set_field(self, menu, model_name, change):
        field = self.env['ir.model.fields'].sudo()._get(model_name, change.get('field'))
        if not field:
            raise UserError(_("This field does not exist."))
        mode = change.get('mode')
        if mode not in FIELD_MODES:
            raise UserError(_("Unknown field mode: %s", mode))
        line = self.field_ids.filtered(lambda line: line.field_id == field)
        values = {'mode': mode, 'condition': (change.get('condition') or '').strip() or False}
        if 'no_export' in change:
            values['no_export'] = bool(change['no_export'])
        no_export = values.get('no_export', line.no_export)
        if mode == 'keep' and not no_export and not (line and (line.no_open or line.no_create or line.field_domain)):
            line.unlink()
        elif line:
            _om_write_changes(line, values)
        else:
            self.env['om.access.profile.field'].create(dict(
                values, profile_id=self.id, model_id=field.model_id.id, field_id=field.id))

    def _om_set_button(self, menu, model_name, change):
        button_type, name = change.get('button_type'), change.get('button_name')
        lines = self.button_ids.filtered(
            lambda line: line.model_id.model == model_name and line.button_type == button_type
            and line.button_name == name)
        mode = change.get('mode')
        if mode == 'visible':
            lines.unlink()
            return
        if mode not in ('hide', 'block', 'hide_block'):
            raise UserError(_("Unknown button mode: %s", mode))
        values = {'mode': mode, 'condition': (change.get('condition') or '').strip() or False}
        if lines:
            lines.write(values)
        else:
            self.env['om.access.profile.button'].create(dict(
                values, profile_id=self.id, model_id=self.env['ir.model']._get(model_name).id,
                view_type='any', button_type=button_type, button_name=name,
                button_label=change.get('label') or name))

    def _om_set_element(self, menu, model_name, change):
        element_type, name = change.get('element_type'), change.get('element_name') or ''
        line = self.element_ids.filtered(
            lambda line: line.model_id.model == model_name and line.element_type == element_type
            and (line.element_name or '') == name)
        if not change.get('hidden'):
            line.unlink()
            return
        values = {'condition': (change.get('condition') or '').strip() or False}
        if line:
            line.write(values)
        else:
            self.env['om.access.profile.element'].create(dict(
                values, profile_id=self.id, model_id=self.env['ir.model']._get(model_name).id,
                element_type=element_type, element_name=name, element_label=change.get('label') or name))

    def _om_set_print(self, menu, model_name, change):
        field_name = 'hidden_report_ids' if change.get('type') == 'ir.actions.report' \
            else ACTION_TYPES.get(change.get('type'))
        if not field_name:
            raise UserError(_("Unknown entry."))
        record = self.env[self._fields[field_name].comodel_name].sudo().browse(change.get('id')).exists()
        if change.get('hidden'):
            self[field_name] |= record
        else:
            self[field_name] -= record

    def _om_set_allowed(self, menu, model_name, change):
        kind = change.get('allowed_kind')
        if kind not in ALLOWED_KINDS:
            raise UserError(_("Unknown kind of allowed records: %s", kind))
        Allowed = self.env['om.access.allowed']
        lines = self.allowed_ids.filtered(lambda line: line.kind == kind)
        if 'per_user' in change:
            per_user = lines.filtered('per_user')
            if change['per_user'] and not per_user:
                Allowed.create({'profile_id': self.id, 'kind': kind, 'per_user': True})
            elif not change['per_user']:
                per_user.unlink()
        if change.get('add'):
            if not lines.filtered(lambda line: line.res_id == change['add'] and not line.per_user):
                Allowed.create({'profile_id': self.id, 'kind': kind, 'res_id': change['add']})
        if change.get('remove'):
            lines.filtered(lambda line: line.id == change['remove']).unlink()
