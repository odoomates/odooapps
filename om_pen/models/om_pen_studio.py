import logging
import uuid

from lxml import etree

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError, ValidationError

from . import om_pen_arch as archlib
from .om_pen_preview import DRAFT_OPTION
from .om_pen_view import KEY_PREFIX

_logger = logging.getLogger(__name__)

EDITABLE_VIEW_TYPES = ('form', 'list', 'kanban', 'search', 'calendar', 'pivot', 'graph', 'activity')
# view types an action can show in Community, and the ones a model can always have
ACTION_VIEW_TYPES = ('list', 'form', 'kanban', 'calendar', 'pivot', 'graph', 'activity')

# what can be changed on each tag, and how the value is checked
TEXT_ATTRS = {'string', 'help', 'placeholder', 'title', 'bg_color', 'icon', 'confirm',
              'widget', 'class', 'name', 'sum', 'avg', 'optional', 'editable', 'default_order',
              'default_group_by', 'limit', 'groups', 'type', 'interval', 'date_start',
              'date_stop', 'date_delay', 'color', 'mode', 'all_day', 'filter_domain', 'operator',
              'nolabel', 'colspan', 'col', 'stacked', 'order', 'disable_linking',
              'display_quantity', 'event_open_popup', 'quick_create', 'records_draggable',
              'group_create', 'create', 'edit', 'delete', 'duplicate', 'import', 'export_xlsx',
              'multi_edit', 'open_form_view', 'sample', 'highlight_color', 'avatar_field',
              'decoration-danger', 'decoration-warning', 'decoration-success',
              'decoration-info', 'decoration-muted', 'decoration-bf', 'decoration-it',
              'string_attr', 'expand', 'default_scale', 'scales'}
EXPRESSION_ATTRS = {'invisible', 'readonly', 'required', 'column_invisible'}
LITERAL_ATTRS = {'domain', 'context', 'options'}
ALLOWED_ATTRS = TEXT_ATTRS | EXPRESSION_ATTRS | LITERAL_ATTRS


def new_name(kind):
    return 'x_pen_%s_%s' % (kind, uuid.uuid4().hex[:6])


class OmPenStudio(models.AbstractModel):
    _name = 'om.pen.studio'
    _description = "Odoo Mates Pen Studio"

    # ------------------------------------------------------------------
    # access
    # ------------------------------------------------------------------

    @api.model
    def _check(self):
        if not self.env.user.has_group('om_pen.group_customizer'):
            raise AccessError(_("You are not allowed to use the Studio."))

    @api.model
    def _check_admin(self):
        self._check()
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_("Only a system administrator can change the data model."))

    @api.model
    def _customization(self, customization_id):
        self._check()
        customization = self.env['om.pen.view'].browse(int(customization_id)).exists()
        if not customization:
            raise UserError(_("This customization does not exist any more. Reload the Studio."))
        return customization

    # ------------------------------------------------------------------
    # opening
    # ------------------------------------------------------------------

    @api.model
    def studio_open(self, model, view_type='form', view_id=False, action_id=False):
        """ What the editor needs to start on a model and a view type.

        A view of that type is created from the model's default arch when the model
        has none, because a customization always extends a real view.
        """
        self._check()
        if model not in self.env:
            raise UserError(_("The model %s does not exist.", model))
        if view_type not in EDITABLE_VIEW_TYPES:
            view_type = 'form'
        action = self.env['ir.actions.act_window'].browse(int(action_id or 0)).exists()
        if action and action.res_model != model:
            action = self.env['ir.actions.act_window']
        if not view_id and action:
            view_id = next((vid for vid, vtype in (action.views or []) if vtype == view_type and vid), False)
            if not view_id and view_type == 'search' and action.search_view_id:
                view_id = action.search_view_id.id
        view = self._primary_view(model, view_type, view_id)
        customization = self.env['om.pen.view']._get_or_create(model, view.id, view_type)
        return {
            'customization_id': customization.id,
            'model': model,
            'model_name': self.env['ir.model']._get(model).name,
            'view_type': view_type,
            'view_id': view.id,
            'view_name': view.name,
            'action': self._action_info(action),
            'has_chatter': self._has_mail(model),
            'is_admin': self.env.user.has_group('base.group_system'),
        }

    @api.model
    def _has_mail(self, model):
        return 'mail.thread' in self.env and isinstance(self.env[model], self.env.registry['mail.thread'])

    @api.model
    def _action_info(self, action):
        if not action:
            return False
        return {
            'id': action.id,
            'name': action.name,
            'view_types': [mode for mode in (action.view_mode or '').split(',') if mode],
            'help': action.help or '',
        }

    @api.model
    def _primary_view(self, model, view_type, view_id=False):
        View = self.env['ir.ui.view'].sudo()
        view = View.browse(int(view_id or 0)).exists()
        while view and view.mode != 'primary' and view.inherit_id:
            view = view.inherit_id
        if view and (view.model != model or view.type != view_type):
            view = View
        if not view:
            view = View.browse(View.default_view(model, view_type))
        if not view:
            view = self._create_default_view(model, view_type)
        return view

    @api.model
    def _create_default_view(self, model, view_type):
        """ A real view holding the arch the model would make up on the fly. """
        Model = self.env[model]
        if view_type == 'calendar':
            arch = self._default_calendar_arch(model)
        else:
            try:
                arch = getattr(Model, '_get_default_%s_view' % view_type)()
            except AttributeError as error:
                raise UserError(_("%(model)s cannot have a %(type)s view.",
                                  model=model, type=view_type)) from error
        name = '%s%s.%s' % (KEY_PREFIX, model, view_type)
        return self.env['ir.ui.view'].sudo().create({
            'name': name,
            'key': name,
            'model': model,
            'type': view_type,
            'arch': etree.tostring(arch, encoding='unicode'),
            'priority': 32,
        })

    @api.model
    def _default_calendar_arch(self, model):
        fields_ = self.env[model]._fields
        date_field = next((name for name, field in fields_.items()
                           if field.type in ('date', 'datetime') and field.store
                           and name not in ('create_date', 'write_date')), None)
        date_field = date_field or 'create_date'
        arch = etree.Element('calendar', date_start=date_field)
        if self.env[model]._rec_name:
            etree.SubElement(arch, 'field', name=self.env[model]._rec_name)
        return arch

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    @api.model
    def _draft_arch(self, customization, strict=False):
        """ The arch of the view with the unpublished changes applied.

        :return: (arch, view, failed) where failed lists the positions of the changes
            that could not be applied any more
        """
        Model = self.env[customization.model].with_context(**{DRAFT_OPTION: True})
        arch, view = Model._get_view(customization.view_id.id, customization.view_type)
        legacy = etree.fromstring(customization._render_arch(draft=True, with_ops=False))
        if len(legacy):
            arch = view._om_pen_apply_leniently(arch, legacy)
        failed = []
        for index, operation in enumerate(customization.draft_ops or []):
            spec = etree.fromstring(operation['spec'])
            try:
                arch = view.apply_inheritance_specs(arch, spec)
            except (ValidationError, ValueError) as error:
                if strict:
                    raise UserError(_("This change cannot be applied: %s", error)) from error
                failed.append(index)
        return arch, view, failed

    @api.model
    def studio_view(self, customization_id, show_hidden=False):
        """ The draft view, numbered for the editor, ready for the web client. """
        customization = self._customization(customization_id)
        return self._view_payload(customization, show_hidden=show_hidden)

    @api.model
    def _view_payload(self, customization, show_hidden=False, strict=False):
        arch, view, failed = self._draft_arch(customization, strict=strict)
        nodes = archlib.annotate(arch, show_hidden=show_hidden)
        self._describe_nodes(customization, arch, nodes)
        Model = self.env[customization.model]
        try:
            processed, models_ = Model._get_view_postprocessed(view, arch)
        except (ValidationError, ValueError) as error:
            raise UserError(_("The view cannot be shown with these changes: %s", error)) from error
        models_ = Model._get_view_fields(customization.view_type, models_)
        node = etree.fromstring(processed) if isinstance(processed, str) else processed
        node = self.env['ir.ui.view']._postprocess_access_rights(node)
        attributes = self.env['ir.ui.view']._get_view_field_attributes()
        related = {
            model: {'fields': self.env[model].fields_get(allfields=list(names), attributes=attributes)}
            for model, names in models_.items()
        }
        # every field of the model itself: grouping and sorting in the canvas may use
        # fields the arch does not show
        related[customization.model] = {'fields': Model.fields_get(attributes=attributes)}
        ops = customization.draft_ops or []
        return {
            'customization_id': customization.id,
            'model': customization.model,
            'view_type': customization.view_type,
            'view_id': customization.view_id.id,
            'arch': etree.tostring(node, encoding='unicode'),
            'fields': related.get(customization.model, {}).get('fields', {}),
            'related_models': related,
            'all_fields': self._fields_info(customization.model),
            'nodes': nodes,
            'failed': [ops[index].get('label') for index in failed],
            'revision': customization._revision(),
            'can_undo': bool(customization.undo_ops),
            'can_redo': bool(customization.redo_ops),
            'has_draft': customization.has_draft,
            'draft_count': customization.draft_count,
            'history': [op.get('label') for op in ops],
            'legacy_rules': len(customization.rule_ids) + len(customization.page_ids),
        }

    @api.model
    def _describe_nodes(self, customization, arch, nodes):
        """ Add to each node what the panel shows about it. """
        for index, node in enumerate(archlib.elements(arch)):
            info = nodes.get(index)
            if not info:
                continue
            info['model'] = self._node_model(customization.model, info.get('owners') or [])
            if info['tag'] == 'field':
                Model = self.env.get(info['model'])
                field = Model._fields.get(info['attrs'].get('name')) if Model is not None else None
                if field:
                    info['field_type'] = field.type
                    info['field_string'] = field._description_string(self.env)
                    info['relation'] = field.comodel_name if field.relational else False
                    info['custom'] = field.manual
                    info['subviews'] = [child.tag for child in node
                                        if archlib.is_element(child) and child.tag in ('list', 'form', 'kanban')]

    @api.model
    def _node_model(self, model, owners):
        for name in owners:
            field = self.env[model]._fields.get(name)
            if not field or not field.relational:
                return model
            model = field.comodel_name
        return model

    @api.model
    def _fields_info(self, model):
        """ Every field of the model, for the Existing Fields list and the pickers. """
        result = {}
        for name, field in self.env[model]._fields.items():
            if name in models.MAGIC_COLUMNS and name not in ('create_date', 'write_date', 'create_uid', 'write_uid'):
                continue
            result[name] = {
                'name': name,
                'string': field._description_string(self.env),
                'type': field.type,
                'relation': field.comodel_name if field.relational else False,
                'store': bool(field.store),
                'custom': bool(field.manual),
                'readonly': bool(field.readonly),
                'required': bool(field.required),
                'related': bool(field.related),
            }
        return result

    # ------------------------------------------------------------------
    # changing
    # ------------------------------------------------------------------

    @api.model
    def studio_change(self, customization_id, revision, changes, show_hidden=False):
        """ Apply one step made of one or more changes, as a single undo step.

        Each change names nodes by the ids of the arch the editor is showing. The step
        is checked by rendering the view with it: a change that does not survive is
        refused and nothing is kept.
        """
        customization = self._customization(customization_id)
        if revision and revision != customization._revision():
            raise UserError(_("The view was changed elsewhere in the meantime. Reload the Studio."))
        if isinstance(changes, dict):
            changes = [changes]
        try:
            with self.env.cr.savepoint():
                before = list(customization.draft_ops or [])
                ops = list(before)
                for change in changes:
                    # every change locates its nodes on the arch as the previous ones
                    # of this step left it
                    customization.draft_ops = ops
                    arch, _view, _failed = self._draft_arch(customization)
                    built, label = self._change_specs(customization, arch, change)
                    ops = ops + [{'spec': archlib.to_string(spec), 'label': label} for spec in built]
                customization.draft_ops = before
                # the whole step is one undo step
                customization._set_draft(ops)
                result = self._view_payload(customization, show_hidden=show_hidden, strict=True)
        except (ValidationError, ValueError) as error:
            raise UserError(str(error)) from error
        return result

    @api.model
    def _target(self, arch, node_id):
        node = archlib.node_by_id(arch, node_id)
        if node is None or node.tag in archlib.UNRENDERED_TAGS:
            raise UserError(_("This element is not on the view any more. Reload the Studio."))
        return node

    @api.model
    def _change_specs(self, customization, arch, change):
        """ Turn one change of the editor into inheritance specs and a label. """
        kind = change.get('op')
        if kind == 'attrs':
            node = self._target(arch, change.get('node'))
            values = self._check_attrs(customization, node, change.get('values') or {})
            return [archlib.attributes_spec(archlib.locator(node, arch), values)], \
                _("Changed %s", self._label(customization, node))
        if kind == 'remove':
            node = self._target(arch, change.get('node'))
            if node is arch:
                raise UserError(_("The view itself cannot be removed."))
            return [archlib.spec(archlib.locator(node, arch), 'replace')], \
                _("Removed %s", self._label(customization, node))
        if kind == 'move':
            node = self._target(arch, change.get('node'))
            target = self._target(arch, change.get('target'))
            position = self._position(change.get('position'))
            if node is target or target in node.iterdescendants():
                raise UserError(_("An element cannot be moved into itself."))
            if node is arch:
                raise UserError(_("The view itself cannot be moved."))
            moved = archlib.spec(archlib.locator(node, arch), 'move')
            return [archlib.spec(archlib.locator(target, arch), position, moved)], \
                _("Moved %s", self._label(customization, node))
        if kind == 'insert':
            target = self._target(arch, change.get('target'))
            position = self._position(change.get('position'))
            if target is arch and position != 'inside':
                position = 'inside'
            model = self._node_model(customization.model, [
                owner.get('name') for owner in reversed(list(target.iterancestors('field')))
            ] + ([target.get('name')] if target.tag == 'field' and position == 'inside' else []))
            element = self._build_element(customization, model, target, change.get('element') or {})
            return self._insert_specs(arch, target, position, element), \
                _("Added %s", self._element_label(customization, model, element))
        raise UserError(_("Unknown change: %s", kind))

    @api.model
    def _insert_specs(self, arch, target, position, element):
        return [archlib.spec(archlib.locator(target, arch), position, element)]

    @api.model
    def _position(self, position):
        if position not in ('before', 'after', 'inside'):
            raise UserError(_("Unknown position: %s", position))
        return position

    @api.model
    def _label(self, customization, node):
        if node.tag == 'field':
            model = self._node_model(customization.model, [
                owner.get('name') for owner in reversed(list(node.iterancestors('field')))])
            field = self.env[model]._fields.get(node.get('name'))
            caption = node.get('string') or (field and field._description_string(self.env)) or node.get('name')
            return caption
        caption = node.get('string') or node.get('title') or node.get('name') or ''
        return ('%s %s' % (node.tag, caption)).strip()

    @api.model
    def _element_label(self, customization, model, element):
        if element.tag == 'field':
            field = self.env[model]._fields.get(element.get('name'))
            return field._description_string(self.env) if field else element.get('name')
        return ('%s %s' % (element.tag, element.get('string') or element.get('title') or '')).strip()

    @api.model
    def _check_attrs(self, customization, node, values):
        clean = {}
        for name, value in values.items():
            if name not in ALLOWED_ATTRS:
                raise UserError(_("%s cannot be changed here.", name))
            if value in (None, False, ''):
                clean[name] = None
                continue
            value = str(value)
            try:
                if name in EXPRESSION_ATTRS:
                    archlib.check_expression(value)
                elif name in LITERAL_ATTRS:
                    archlib.check_literal(value)
            except (ValueError, SyntaxError) as error:
                raise UserError(_("%(attribute)s is not valid: %(value)s", attribute=name, value=value)) from error
            if name == 'groups':
                value = self._check_groups(value)
            clean[name] = value
        if node.tag == 'field' and 'name' in clean:
            raise UserError(_("A field keeps its name; add another field instead."))
        return clean

    @api.model
    def _check_groups(self, value):
        """ groups= takes external ids; make sure each of them is a group. """
        for xmlid in value.split(','):
            xmlid = xmlid.strip().lstrip('!')
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if not record or record._name != 'res.groups':
                raise UserError(_("%s is not a group.", xmlid))
        return value

    # ------------------------------------------------------------------
    # building new elements
    # ------------------------------------------------------------------

    @api.model
    def _build_element(self, customization, model, target, element):
        """ The node to insert, built here from a description, never taken as raw xml. """
        kind = element.get('kind')
        view_type = customization.view_type
        attrs = element.get('attrs') or {}
        if kind == 'field':
            name = element.get('name')
            if name not in self.env[model]._fields:
                raise UserError(_("%(model)s has no field %(field)s.", model=model, field=name))
            node = etree.Element('field', name=name)
            if view_type in ('pivot', 'graph') and attrs.get('type'):
                node.set('type', attrs['type'])
            for attribute, value in attrs.items():
                if attribute in ('widget', 'string', 'optional', 'type', 'interval', 'filter_domain',
                                 'operator', 'sum', 'avg') and value:
                    node.set(attribute, str(value))
            return node
        if kind == 'notebook':
            notebook = etree.Element('notebook')
            page = etree.SubElement(notebook, 'page', name=new_name('page'),
                                    string=element.get('string') or _("New Tab"))
            self._two_columns(page)
            return notebook
        if kind == 'page':
            page = etree.Element('page', name=new_name('page'), string=element.get('string') or _("New Tab"))
            self._two_columns(page)
            return page
        if kind == 'columns':
            group = etree.Element('group', name=new_name('group'))
            self._two_columns(group, wrap=False)
            return group
        if kind == 'group':
            return etree.Element('group', name=new_name('group'), string=element.get('string') or _("New Group"))
        if kind == 'separator':
            return etree.Element('separator', string=element.get('string') or _("New Section"))
        if kind == 'ribbon':
            node = etree.Element('widget', name='web_ribbon', title=element.get('string') or _("Archived"),
                                 bg_color=element.get('bg_color') or 'text-bg-danger')
            if element.get('invisible'):
                archlib.check_expression(element['invisible'])
                node.set('invisible', element['invisible'])
            return node
        if kind == 'chatter':
            if not self._has_mail(model):
                raise UserError(_("Only a model with a chatter can show one. Turn on the chatter for this model first."))
            return etree.Element('chatter')
        if kind == 'filter':
            return self._build_filter(model, element)
        if kind == 'groupby':
            field = element.get('field')
            if field not in self.env[model]._fields:
                raise UserError(_("%(model)s has no field %(field)s.", model=model, field=field))
            return etree.Element('filter', name=new_name('groupby'),
                                 string=element.get('string') or self.env[model]._fields[field].string,
                                 context="{'group_by': %r}" % field)
        if kind == 'search_separator':
            return etree.Element('separator')
        if kind == 'button':
            return self._build_button(model, element)
        if kind == 'smart_button':
            raise UserError(_("A smart button is added from its own dialog."))
        raise UserError(_("Unknown element: %s", kind))

    @api.model
    def _two_columns(self, parent, wrap=True):
        holder = etree.SubElement(parent, 'group', name=new_name('group')) if wrap else parent
        etree.SubElement(holder, 'group', name=new_name('group'))
        etree.SubElement(holder, 'group', name=new_name('group'))

    @api.model
    def _build_filter(self, model, element):
        domain = element.get('domain') or '[]'
        archlib.check_literal(domain)
        node = etree.Element('filter', name=new_name('filter'),
                             string=element.get('string') or _("New Filter"), domain=domain)
        return node

    @api.model
    def _build_button(self, model, element):
        """ A header button opening an action. """
        action = self.env['ir.actions.actions'].sudo().browse(int(element.get('action_id') or 0)).exists()
        if not action:
            raise UserError(_("Pick the action the button runs."))
        node = etree.Element('button', name=str(action.id), type='action',
                             string=element.get('string') or action.name)
        node.set('class', 'btn-primary' if element.get('primary') else 'btn-secondary')
        if element.get('confirm'):
            node.set('confirm', element['confirm'])
        return node

    # ------------------------------------------------------------------
    # history
    # ------------------------------------------------------------------

    @api.model
    def studio_undo(self, customization_id, show_hidden=False):
        customization = self._customization(customization_id)
        customization._undo()
        return self._view_payload(customization, show_hidden=show_hidden)

    @api.model
    def studio_redo(self, customization_id, show_hidden=False):
        customization = self._customization(customization_id)
        customization._redo()
        return self._view_payload(customization, show_hidden=show_hidden)

    @api.model
    def studio_publish(self, customization_id, show_hidden=False):
        customization = self._customization(customization_id)
        if not customization.has_draft:
            raise UserError(_("There is nothing waiting to be published."))
        # refuse a change that does not apply any more, rather than publish it broken
        self._draft_arch(customization, strict=True)
        customization.action_publish()
        return self._view_payload(customization, show_hidden=show_hidden)

    @api.model
    def studio_discard(self, customization_id, show_hidden=False):
        customization = self._customization(customization_id)
        customization.action_discard_draft()
        return self._view_payload(customization, show_hidden=show_hidden)

    @api.model
    def studio_reset(self, customization_id, show_hidden=False):
        """ Back to the original view, as a draft: nothing changes until published. """
        customization = self._customization(customization_id)
        customization.rule_ids._forget()
        for page in customization.page_ids:
            if page.published:
                page.to_remove = True
            else:
                page.unlink()
        customization._set_draft([])
        return self._view_payload(customization, show_hidden=show_hidden)

    @api.model
    def studio_versions(self, customization_id):
        customization = self._customization(customization_id)
        return [{
            'id': version.id,
            'date': version.create_date,
            'user': version.create_uid.name,
            'changes': version.change_count,
        } for version in customization.version_ids]

    @api.model
    def studio_version_diff(self, version_id):
        self._check()
        version = self.env['om.pen.version'].browse(int(version_id)).exists()
        if not version:
            raise UserError(_("This version does not exist any more."))
        return version._diff()

    @api.model
    def studio_version_restore(self, version_id, show_hidden=False):
        self._check()
        version = self.env['om.pen.version'].browse(int(version_id)).exists()
        if not version:
            raise UserError(_("This version does not exist any more."))
        version._restore()
        return self._view_payload(version.customize_id, show_hidden=show_hidden)

    # ------------------------------------------------------------------
    # pickers
    # ------------------------------------------------------------------

    @api.model
    def studio_groups(self):
        self._check()
        groups = self.env['res.groups'].search([])
        xmlids = groups.get_external_id()
        return [{'id': group.id, 'name': group.display_name, 'xmlid': xmlids.get(group.id)}
                for group in groups if xmlids.get(group.id)]

    @api.model
    def studio_models(self):
        self._check()
        return [{'model': record.model, 'name': record.name}
                for record in self.env['ir.model'].search([('transient', '=', False)], order='name')
                if record.model in self.env and not self.env[record.model]._abstract]

    @api.model
    def studio_actions(self, model):
        """ Actions a header button can run on a record of `model`. """
        self._check()
        model_id = self.env['ir.model']._get_id(model)
        actions = self.env['ir.actions.server'].search([('model_id', '=', model_id)])
        return [{'id': action.id, 'name': action.name} for action in actions]

    @api.model
    def studio_action_add_view(self, action_id, view_type):
        """ Show one more view type in the app the Studio was opened from. """
        self._check()
        action = self.env['ir.actions.act_window'].browse(int(action_id)).exists()
        if not action:
            raise UserError(_("This action does not exist any more."))
        if view_type not in ACTION_VIEW_TYPES:
            raise UserError(_("%s views cannot be added here.", view_type))
        if view_type == 'activity' and not self._has_mail(action.res_model):
            raise UserError(_("Only a model with a chatter can have an activity view."))
        self._primary_view(action.res_model, view_type)
        modes = [mode for mode in (action.view_mode or '').split(',') if mode]
        if view_type not in modes:
            modes.append(view_type)
            action.sudo().view_mode = ','.join(modes)
        return True
