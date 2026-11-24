import json
import re

from odoo import Command, _, api, models
from odoo.exceptions import UserError

# kinds of new fields the Add tab offers: the field type, and the widget that goes with it
NEW_FIELDS = {
    'char': ('char', None),
    'text': ('text', None),
    'html': ('html', 'html'),
    'integer': ('integer', None),
    'float': ('float', None),
    'monetary': ('monetary', 'monetary'),
    'boolean': ('boolean', None),
    'date': ('date', None),
    'datetime': ('datetime', None),
    'selection': ('selection', None),
    'priority': ('selection', 'priority'),
    'many2one': ('many2one', None),
    'one2many': ('one2many', None),
    'many2many': ('many2many', 'many2many_tags'),
    'binary': ('binary', None),
    'image': ('binary', 'image'),
    'signature': ('binary', 'signature'),
    'related': (None, None),
    'total': (None, None),
}
PRIORITY_SELECTION = [('0', "Normal"), ('1', "Low"), ('2', "High"), ('3', "Very High")]


class OmPenStudio(models.AbstractModel):
    _inherit = 'om.pen.studio'

    @api.model
    def studio_create_field(self, customization_id, revision, values, target, position, show_hidden=False):
        """ Create a field and put it where it was dropped, as one undo step. """
        customization = self._customization(customization_id)
        self._check_admin()
        if revision and revision != customization._revision():
            raise UserError(_("The view was changed elsewhere in the meantime. Reload the Studio."))
        arch, _view, _failed = self._draft_arch(customization)
        target_node = self._target(arch, target)
        owners = [owner.get('name') for owner in reversed(list(target_node.iterancestors('field')))]
        model = self._node_model(customization.model, owners)
        name, widget = self._create_field(model, values)
        element = {'kind': 'field', 'name': name, 'attrs': {'widget': widget} if widget else {}}
        return self.studio_change(customization.id, revision, [{
            'op': 'insert', 'target': target, 'position': position, 'element': element,
        }], show_hidden=show_hidden)

    @api.model
    def _create_field(self, model, values):
        """ Create a manual field from what the new field dialog sent.

        :return: (technical name, widget to show it with)
        """
        kind = values.get('kind') or 'char'
        if kind not in NEW_FIELDS:
            raise UserError(_("%s is not a field this Studio can create.", kind))
        ttype, widget = NEW_FIELDS[kind]
        label = (values.get('label') or '').strip()
        if not label:
            raise UserError(_("A new field needs a label."))
        View = self.env['om.pen.view']
        name = (values.get('name') or '').strip()
        name = View._clean_field_name(model, name) if name else View._field_name_for(model, label)
        vals = {
            'name': name,
            'field_description': label,
            'model': model,
            'model_id': self.env['ir.model']._get_id(model),
            'state': 'manual',
            'help': values.get('help') or False,
        }
        if kind == 'related':
            path = (values.get('related') or '').strip()
            target = View.related_target(model, path)
            vals.update(ttype=target['ttype'], related=path, relation=target['relation'] or False,
                        store=False, readonly=True)
        elif kind == 'total':
            vals.update(self._total_values(model, name, values))
        else:
            vals['ttype'] = ttype
            if ttype in ('many2one', 'many2many'):
                relation = values.get('relation')
                if not relation or relation not in self.env:
                    raise UserError(_("Pick the model to link to."))
                vals['relation'] = relation
                if ttype == 'many2one':
                    vals['on_delete'] = 'set null'
            if ttype == 'one2many':
                vals.update(self._one2many_values(model, values))
            if kind == 'priority':
                vals['selection_ids'] = [
                    Command.create({'value': value, 'name': string, 'sequence': index})
                    for index, (value, string) in enumerate(PRIORITY_SELECTION)]
            elif ttype == 'selection':
                options = [line.strip() for line in (values.get('selection') or '').splitlines() if line.strip()]
                if not options:
                    raise UserError(_("A selection needs at least one option."))
                vals['selection_ids'] = [
                    Command.create({'value': self._selection_value(option, index), 'name': option,
                                    'sequence': index})
                    for index, option in enumerate(options, start=1)]
            if ttype == 'monetary':
                vals['currency_field'] = self._currency_field(model)
        self.env['ir.model.fields'].sudo().with_context(update_custom_fields=True).create(vals)
        return name, widget

    @api.model
    def _selection_value(self, option, index):
        slug = re.sub(r'[^a-z0-9]+', '_', option.lower()).strip('_')[:40]
        return slug or 'value_%s' % index

    @api.model
    def _currency_field(self, model):
        """ The currency an amount is in; a model without one gets one. """
        for name in ('currency_id', 'x_currency_id', 'x_studio_currency_id'):
            if name in self.env[model]._fields:
                return name
        self.env['ir.model.fields'].sudo().with_context(update_custom_fields=True).create({
            'name': 'x_currency_id',
            'field_description': _("Currency"),
            'model': model,
            'model_id': self.env['ir.model']._get_id(model),
            'ttype': 'many2one',
            'relation': 'res.currency',
            'state': 'manual',
        })
        # amounts need a currency to show in: the company's by default
        self.env['ir.default'].sudo().set(model, 'x_currency_id', self.env.company.currency_id.id)
        return 'x_currency_id'

    @api.model
    def _one2many_values(self, model, values):
        relation = values.get('relation')
        if not relation or relation not in self.env:
            raise UserError(_("Pick the model of the lines."))
        inverse = values.get('relation_field')
        comodel = self.env[relation]
        if inverse:
            field = comodel._fields.get(inverse)
            if not field or field.type != 'many2one' or field.comodel_name != model:
                raise UserError(_("%(field)s is not a link from %(lines)s back to %(model)s.",
                                  field=inverse, lines=relation, model=model))
        else:
            # no link back yet: make one, the lines cannot exist without it
            inverse = self.env['om.pen.view']._field_name_for(relation, model.replace('.', '_'))
            self.env['ir.model.fields'].sudo().with_context(update_custom_fields=True).create({
                'name': inverse,
                'field_description': self.env['ir.model']._get(model).name,
                'model': relation,
                'model_id': self.env['ir.model']._get_id(relation),
                'ttype': 'many2one',
                'relation': model,
                'on_delete': 'cascade',
                'state': 'manual',
            })
        return {'relation': relation, 'relation_field': inverse}

    @api.model
    def _total_values(self, model, name, values):
        """ A count, or a sum of a field, over the lines of an x2many. """
        lines = values.get('lines')
        field = self.env[model]._fields.get(lines)
        if not field or field.type not in ('one2many', 'many2many'):
            raise UserError(_("Pick the lines to count or add up."))
        operation = values.get('operation') or 'count'
        if operation == 'count':
            code = "for record in self:\n    record[%r] = len(record[%r])" % (name, lines)
            return {'ttype': 'integer', 'compute': code, 'depends': lines, 'store': False, 'readonly': True}
        measure = values.get('measure')
        measured = self.env[field.comodel_name]._fields.get(measure)
        if not measured or measured.type not in ('integer', 'float', 'monetary'):
            raise UserError(_("Pick a number of the lines to add up."))
        code = "for record in self:\n    record[%r] = sum(record[%r].mapped(%r))" % (name, lines, measure)
        ttype = 'float' if measured.type == 'monetary' else measured.type
        return {'ttype': ttype, 'compute': code, 'depends': '%s.%s' % (lines, measure),
                'store': False, 'readonly': True}

    # ------------------------------------------------------------------
    # a field's own settings
    # ------------------------------------------------------------------

    @api.model
    def studio_field_info(self, model, field_name):
        """ What the Properties tab shows of the field itself, beyond this view. """
        self._check()
        field = self.env['ir.model.fields']._get(model, field_name)
        if not field:
            raise UserError(_("%(model)s has no field %(field)s.", model=model, field=field_name))
        default = self.env['ir.default'].sudo().search([
            ('field_id', '=', field.id), ('user_id', '=', False), ('company_id', '=', False),
            ('condition', '=', False)], limit=1)
        return {
            'id': field.id,
            'name': field.name,
            'label': field.field_description,
            'help': field.help or '',
            'type': field.ttype,
            'custom': field.state == 'manual',
            'required': field.required,
            'relation': field.relation or False,
            'selection': [{'value': item.value, 'name': item.name} for item in field.selection_ids],
            'default': json.loads(default.json_value) if default else None,
            'compute': bool(field.compute),
            'related': field.related or '',
        }

    @api.model
    def studio_field_save(self, model, field_name, values):
        """ Change a field itself: its label and tooltip everywhere, its default value. """
        self._check_admin()
        field = self.env['ir.model.fields'].sudo()._get(model, field_name)
        if not field:
            raise UserError(_("%(model)s has no field %(field)s.", model=model, field=field_name))
        if 'default' in values:
            value = values['default']
            if value in (None, '', False) and field.ttype != 'boolean':
                self.env['ir.default'].sudo().search([
                    ('field_id', '=', field.id), ('user_id', '=', False), ('company_id', '=', False),
                    ('condition', '=', False)]).unlink()
            else:
                self.env['ir.default'].sudo().set(model, field_name, value)
        if field.state != 'manual':
            return self.studio_field_info(model, field_name)
        vals = {}
        if values.get('label'):
            vals['field_description'] = values['label']
        if 'help' in values:
            vals['help'] = values['help'] or False
        if 'required' in values and field.ttype not in ('one2many', 'many2many', 'boolean') and not field.compute:
            vals['required'] = bool(values['required'])
        if 'selection' in values and field.ttype == 'selection':
            vals['selection_ids'] = self._selection_commands(field, values['selection'])
        if vals:
            field.with_context(update_custom_fields=True).write(vals)
        return self.studio_field_info(model, field_name)

    @api.model
    def _selection_commands(self, field, options):
        """ Keep the values already stored, add the new ones, drop the removed ones. """
        existing = {item.value: item for item in field.selection_ids}
        commands = []
        kept = set()
        for index, option in enumerate(options, start=1):
            value = option.get('value') or self._selection_value(option.get('name') or '', index)
            if value in existing:
                commands.append(Command.update(existing[value].id, {'name': option['name'], 'sequence': index}))
            else:
                commands.append(Command.create({'value': value, 'name': option['name'], 'sequence': index}))
            kept.add(value)
        commands += [Command.delete(item.id) for value, item in existing.items() if value not in kept]
        return commands

    # ------------------------------------------------------------------
    # deleting a field
    # ------------------------------------------------------------------

    @api.model
    def studio_field_impact(self, model, field_name):
        """ Everything that uses a custom field, to show before it is deleted. """
        self._check_admin()
        field = self.env['ir.model.fields']._get(model, field_name)
        if not field or field.state != 'manual':
            raise UserError(_("Only a custom field can be deleted here."))
        pattern = re.compile(r'\b%s\b' % re.escape(field_name))
        usage = []
        views = self.env['ir.ui.view'].sudo().search([('arch_db', 'ilike', field_name)])
        for view in views:
            if pattern.search(view.arch_db or ''):
                usage.append({'kind': _("View"), 'name': view.name})
        for customization in self.env['om.pen.view'].search([]):
            if any(pattern.search(op['spec']) for op in (customization.draft_ops or [])):
                usage.append({'kind': _("Unpublished change"), 'name': customization.display_name})
        for other in self.env['ir.model.fields'].sudo().search([
                ('related', 'ilike', field_name)]) | self.env['ir.model.fields'].sudo().search([
                ('depends', 'ilike', field_name)]):
            if other != field:
                usage.append({'kind': _("Field"), 'name': '%s (%s)' % (other.field_description, other.model)})
        if 'base.automation' in self.env:
            for rule in self.env['base.automation'].sudo().search([('model_id.model', '=', model)]):
                if field in rule.trigger_field_ids or pattern.search(
                        (rule.filter_domain or '') + (rule.filter_pre_domain or '')):
                    usage.append({'kind': _("Automation"), 'name': rule.name})
        for action in self.env['ir.actions.server'].sudo().search([('model_id.model', '=', model)]):
            if pattern.search(action.code or '') or field in action.update_field_id:
                usage.append({'kind': _("Server action"), 'name': action.name})
        records = 0
        Model = self.env[model].sudo()
        if field.store and field.ttype not in ('one2many', 'many2many', 'binary'):
            records = Model.search_count([(field_name, '!=', False)])
        return {'usage': usage, 'records': records, 'label': field.field_description}

    @api.model
    def studio_field_delete(self, model, field_name):
        """ Delete a custom field, after taking it out of the Studio's changes. """
        self._check_admin()
        field = self.env['ir.model.fields'].sudo()._get(model, field_name)
        if not field or field.state != 'manual':
            raise UserError(_("Only a custom field can be deleted here."))
        pattern = re.compile(r'\b%s\b' % re.escape(field_name))
        for customization in self.env['om.pen.view'].search([('model', '=', model)]):
            for attr in ('draft_ops', 'published_ops'):
                ops = customization[attr] or []
                kept = [op for op in ops if not pattern.search(op['spec'])]
                if kept != ops:
                    customization.with_context(om_pen_skip_apply=True)[attr] = kept
            customization.rule_ids.filtered(lambda r: r.field_name == field_name).unlink()
            customization._apply()
        field.with_context(update_custom_fields=True).unlink()
        return True

    @api.model
    def studio_field_defaults(self, model):
        """ Default values set for the model, as the Studio shows them. """
        self._check()
        defaults = self.env['ir.default'].sudo().search([
            ('field_id.model', '=', model), ('user_id', '=', False), ('condition', '=', False)])
        return [{'field': item.field_id.name, 'label': item.field_id.field_description,
                 'value': item.json_value} for item in defaults]
