import logging
import re

from lxml import etree

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# the customization must land after every other extension of the same view
CUSTOMIZATION_PRIORITY = 9999

# xml ids are filed under a module that will never be installed, so a module upgrade
# cannot decide the record is stale and delete it (_process_end, ir_model.py)
XMLID_MODULE = '__custom__'

# field types a non-developer can create safely. Left out on purpose: one2many needs an
# inverse many2one on the target model, and properties / many2one_reference / json are
# not handled by ir.model.fields._instanciate_attrs and would be created broken.
ALLOWED_FIELD_TYPES = [
    ('char', "Text"),
    ('text', "Multiline Text"),
    ('html', "Rich Text"),
    ('integer', "Whole Number"),
    ('float', "Decimal Number"),
    ('monetary', "Money"),
    ('boolean', "Checkbox"),
    ('date', "Date"),
    ('datetime', "Date & Time"),
    ('selection', "Selection"),
    ('many2one', "Link To A Record"),
    ('many2many', "Links To Several Records"),
    ('binary', "File"),
]

# action attributes, and the tags they are allowed on
ACTION_FIELDS = {
    'create_ok': ('create', ('form', 'list', 'kanban')),
    'edit_ok': ('edit', ('form', 'list', 'kanban')),
    'delete_ok': ('delete', ('form', 'list', 'kanban')),
    'duplicate_ok': ('duplicate', ('form', 'list', 'kanban')),
    'export_ok': ('export_xlsx', ('list',)),
    'import_ok': ('import', ('list', 'kanban')),
}


class OmPenView(models.Model):
    _name = 'om.pen.view'
    _description = "View Customization"

    model = fields.Char(string="Model", required=True, index=True)
    view_id = fields.Many2one('ir.ui.view', string="Customized View",
                              required=True, ondelete='cascade', index=True)
    view_type = fields.Char(string="View Type", required=True)
    custom_view_id = fields.Many2one('ir.ui.view', string="Generated View",
                                     ondelete='set null', readonly=True,
                                     help="The inherited view generated from the rules below.")
    active = fields.Boolean(default=True,
                            help="Switch this off to drop every customization of this"
                                 " view without losing the rules.")
    rule_ids = fields.One2many('om.pen.rule', 'customize_id', string="Field Rules")
    page_ids = fields.One2many('om.pen.page', 'customize_id', string="Added Pages")
    has_draft = fields.Boolean(
        string="Has Unpublished Changes", compute='_compute_draft_state')
    draft_count = fields.Integer(string="Unpublished", compute='_compute_draft_state')
    draft_invalid = fields.Boolean(
        string="Draft No Longer Fits", compute='_compute_draft_state',
        help="The unpublished changes point at something the standard view no longer"
             " has, usually after a module update. They cannot be published as they are.")
    broken = fields.Boolean(
        string="Broken", compute='_compute_broken',
        help="The generated view no longer matches the standard view it customizes,"
             " usually because a module update moved or removed something it points at.")

    create_ok = fields.Boolean(string="Allow Creating", default=True)
    edit_ok = fields.Boolean(string="Allow Editing", default=True)
    delete_ok = fields.Boolean(string="Allow Deleting", default=True)
    duplicate_ok = fields.Boolean(string="Allow Duplicating", default=True)
    export_ok = fields.Boolean(string="Allow Exporting", default=True)
    import_ok = fields.Boolean(string="Allow Importing", default=True)

    _view_uniq = models.Constraint(
        'UNIQUE(view_id)',
        "A view can only be customized once.",
    )

    @api.depends('model', 'view_type')
    def _compute_display_name(self):
        for record in self:
            record.display_name = "%s / %s" % (record.model, record.view_type)

    # ------------------------------------------------------------------
    # arch generation
    # ------------------------------------------------------------------

    def _render_arch(self, draft=False):
        """ Build the inheritance spec for this customization.

        By default this renders the **published** state, which is what the live view is
        made of. `draft=True` renders what the editor is working on, and is only used to
        check that it could be published.
        """
        self.ensure_one()
        arch = self.view_id._get_combined_arch()
        root = etree.Element('data')
        # pages first: a field placed inside a page needs the page to exist already,
        # and inheritance specs are applied in document order
        for page in self.page_ids:
            if draft:
                if page.to_remove:
                    continue
            elif not page.published:
                continue
            root.extend(page._render_nodes(arch))
        for rule in self.rule_ids:
            if draft:
                if rule.to_remove:
                    continue
                root.extend(rule._render_nodes(arch))
            elif published := rule._published():
                # a rule that has never been published contributes nothing to the live
                # view, and an empty recordset has no rule to render
                root.extend(published._render_nodes(arch))
        if (node := self._render_action_node()) is not None:
            root.append(node)
        # indented, so the generated view reads properly in Settings > Views and in an
        # exported module
        etree.indent(root, space='    ')
        return etree.tostring(root, encoding='unicode')

    def _render_action_node(self):
        """ Turn the action switches into attributes on the view's root tag. """
        self.ensure_one()
        disabled = {
            attribute: '0'
            for field_name, (attribute, tags) in ACTION_FIELDS.items()
            if self.view_type in tags and not self[field_name]
        }
        if not disabled:
            return None
        spec = etree.Element('xpath', expr='//%s' % self.view_type, position='attributes')
        for attribute, value in disabled.items():
            element = etree.SubElement(spec, 'attribute', name=attribute)
            element.text = value
        return spec

    def _has_customizations(self):
        """ Whether the *published* state changes anything. """
        self.ensure_one()
        if any(page.published for page in self.page_ids):
            return True
        for rule in self.rule_ids:
            published = rule._published()
            if published and (published.kind in ('add', 'move')
                              or published._attribute_values()):
                return True
        return self._render_action_node() is not None

    @api.depends('rule_ids', 'page_ids', 'rule_ids.published_values',
                 'rule_ids.to_remove', 'page_ids.published', 'page_ids.to_remove')
    def _compute_draft_state(self):
        for record in self:
            drafts = [rule for rule in record.rule_ids if rule._is_draft()]
            drafts += [page for page in record.page_ids
                       if not page.published or page.to_remove]
            record.draft_count = len(drafts)
            record.has_draft = bool(drafts)
            record.draft_invalid = bool(drafts) and not record._draft_renders()

    def _assert_draft_renders(self):
        """ Raise if the unpublished state could not be applied. """
        self.ensure_one()
        try:
            self._render_arch(draft=True)
        except ValidationError as error:
            raise UserError(str(error)) from error

    def _draft_renders(self):
        """ Whether the unpublished state could be applied at all. """
        self.ensure_one()
        try:
            self._render_arch(draft=True)
        except (ValidationError, UserError):
            return False
        return True

    @api.depends('custom_view_id')
    def _compute_broken(self):
        """ Flag customizations whose locators no longer resolve.

        ir.ui.view computes this for us; a broken one is what would make the next
        module upgrade fail, so it is worth surfacing before that happens.
        """
        for record in self:
            locators = record.custom_view_id.invalid_locators
            record.broken = bool(locators)

    # ------------------------------------------------------------------
    # applying
    # ------------------------------------------------------------------

    def _apply(self):
        """ Write the generated view, or drop it when nothing is customized.

        Everything goes through the ORM rather than raw SQL so the `templates` cache
        is cleared and the other workers are signalled.
        """
        for record in self:
            if not record.active or not record._has_customizations():
                record.custom_view_id.unlink()
                continue

            # check the unpublished state too, so a change that cannot ever be applied
            # is refused as it is made rather than at publish time
            record._assert_draft_renders()
            values = {'arch': record._render_arch()}
            try:
                if record.custom_view_id:
                    record.custom_view_id.write(values)
                else:
                    # skip_apply, otherwise storing the generated view re-enters write()
                    # and applies the customization a second time
                    record.with_context(om_pen_skip_apply=True).custom_view_id = self.env['ir.ui.view'].create({
                        **values,
                        'name': "%s customization" % record.view_id.name,
                        'model': record.model,
                        'inherit_id': record.view_id.id,
                        'mode': 'extension',
                        'priority': CUSTOMIZATION_PRIORITY,
                        'active': True,
                    })
                    record._ensure_xmlid()
            except (ValidationError, UserError) as error:
                # the arch did not survive _check_xml; report it rather than leaving a
                # broken view behind, because a broken view blocks the next upgrade
                raise UserError(_(
                    "This customization cannot be applied to %(view)s:\n\n%(error)s",
                    view=record.view_id.display_name, error=error,
                )) from error
        self._clear_draft_views()
        return True

    def _clear_draft_views(self):
        """ Forget the cached views built from the draft.

        A draft change touches no ir.ui.view record, so nothing else tells the view
        cache that the previewed view is out of date; a stale one pairs a new arch
        with an old field list and breaks the list renderer.
        """
        self.env.registry.clear_cache('templates')

    def _ensure_xmlid(self):
        """ Give the generated view an external id, so it can be found and exported.

        The module is deliberately one that is never installed: a record filed under an
        installed module is deleted on that module's next upgrade when it is not in the
        data files.
        """
        self.ensure_one()
        if not self.custom_view_id:
            return
        name = 'om_pen_view_%s' % self.id
        existing = self.env['ir.model.data'].search([
            ('module', '=', XMLID_MODULE), ('name', '=', name)], limit=1)
        if existing:
            existing.res_id = self.custom_view_id.id
            return
        self.env['ir.model.data'].create({
            'module': XMLID_MODULE,
            'name': name,
            'model': 'ir.ui.view',
            'res_id': self.custom_view_id.id,
            'noupdate': True,
        })

    def action_publish(self):
        """ Make the unpublished changes the live ones.

        One transaction: if the generated arch does not survive validation nothing is
        published, so a half-applied customization cannot exist.
        """
        for record in self:
            record.rule_ids.filtered('to_remove').unlink()
            record.page_ids.filtered('to_remove').unlink()
            for rule in record.rule_ids:
                rule.published_values = rule._snapshot()
            record.page_ids.published = True
            record._apply()
        return True

    def action_discard_draft(self):
        """ Throw the unpublished changes away and go back to what is live. """
        for record in self:
            record.rule_ids.filtered(lambda r: not r.published_values).unlink()
            record.page_ids.filtered(lambda p: not p.published).unlink()
            for rule in record.rule_ids:
                values = dict(rule.published_values)
                values['group_ids'] = [Command.set(values.get('group_ids') or [])]
                rule.write({**values, 'to_remove': False})
            record.page_ids.to_remove = False
        self._clear_draft_views()
        return True

    def action_reset(self):
        """ Drop every rule and the generated view. """
        self.rule_ids.unlink()
        self.custom_view_id.unlink()
        return True

    # the fields the generated arch is built from; writing anything else leaves it alone
    ARCH_FIELDS = {'active', 'view_id', 'rule_ids', 'page_ids', *ACTION_FIELDS}

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('om_pen_skip_apply') and self.ARCH_FIELDS & set(vals):
            self._apply()
        return result

    # ------------------------------------------------------------------
    # client interface
    # ------------------------------------------------------------------

    @api.model
    def _get_or_create(self, model, view_id, view_type):
        self._check_customizer()
        customization = self.search([('view_id', '=', view_id)], limit=1)
        if not customization:
            customization = self.with_context(om_pen_skip_apply=True).create({
                'model': model,
                'view_id': view_id,
                'view_type': view_type,
            })
        return customization

    @api.model
    def get_customization(self, model, view_id, view_type):
        """ Return what the panel needs to prefill itself. """
        self._check_customizer()
        customization = self.search([('view_id', '=', view_id)], limit=1)
        if not customization:
            return {
                'rules': {},
                'actions': {name: True for name in ACTION_FIELDS},
                'pages': [],
                'broken': False,
                'has_draft': False,
                'draft_count': 0,
                'draft_invalid': False,
            }
        return {
            'rules': {
                (('%s/%s/' % (rule.sub_field, rule.sub_view_type)) if rule.sub_field
                 else '') + rule.field_name: {
                    'label': rule.label or '',
                    'help_text': rule.help_text or '',
                    'widget': rule.widget or '',
                    'placeholder': rule.placeholder or '',
                    'optional': rule.optional or '',
                    'invisible': rule.invisible or '',
                    'readonly': rule.readonly or '',
                    'required': rule.required or '',
                    'column_invisible': rule.column_invisible or '',
                    'opt_no_open': rule.opt_no_open,
                    'opt_no_create': rule.opt_no_create,
                    'opt_no_quick_create': rule.opt_no_quick_create,
                    'opt_no_create_edit': rule.opt_no_create_edit,
                    'kind': rule.kind,
                    'group_ids': rule.group_ids.ids,
                    'anchor_field': rule.anchor_field or '',
                    'position': rule.position or 'after',
                    'sub_field': rule.sub_field or '',
                    'sub_view_type': rule.sub_view_type or '',
                    'condition_data': rule.condition_data or {},
                    'draft': rule._is_draft(),
                    'to_remove': rule.to_remove,
                }
                for rule in customization.rule_ids
            },
            'actions': {name: customization[name] for name in ACTION_FIELDS},
            'pages': [
                {'id': page.id, 'name': page.name, 'string': page.string}
                for page in customization.page_ids
            ],
            'broken': customization.broken,
            'has_draft': customization.has_draft,
            'draft_count': customization.draft_count,
            'draft_invalid': customization.draft_invalid,
        }

    @api.model
    def _split_key(self, key):
        """ Rules of embedded views are keyed `<x2many>/<list|form>/<field>`.

        A bare field name means the view itself, which keeps every existing caller
        working unchanged.
        """
        parts = (key or '').split('/')
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        return '', False, key

    @api.model
    def save_field_rule(self, model, view_id, view_type, field_name, values):
        """ Upsert the rule for one field and regenerate the view. """
        customization = self._get_or_create(model, view_id, view_type)
        sub_field, sub_view_type, field_name = self._split_key(field_name)
        values = dict(values)
        # the caption the user clicked: it tells which of several captions to rename
        shown_label = values.pop('shown_label', None)
        if 'group_ids' in values:
            # a bare list of ids is ambiguous on a many2many; be explicit
            values['group_ids'] = [Command.set(values['group_ids'] or [])]
        rule = customization.rule_ids.filtered(
            lambda r: r.field_name == field_name and (r.sub_field or '') == sub_field
            and (r.sub_view_type or False) == sub_view_type)
        if rule:
            rule.write({**values, 'to_remove': False})
        else:
            rule = self.env['om.pen.rule'].create({
                **values,
                'customize_id': customization.id,
                'field_name': field_name,
                'sub_field': sub_field,
                'sub_view_type': sub_view_type,
            })
        if not rule.label:
            rule.label_scope = False
        elif shown_label and not sub_field:
            # an already renamed field shows its new label, which matches nothing in
            # the arch: keep the scope found when it was first renamed
            scope = rule._label_scope_for(customization.view_id._get_combined_arch(), shown_label)
            if scope is not None or not rule.label_scope:
                rule.label_scope = scope
        if rule.kind == 'tweak' and not rule._attribute_values():
            # the user cleared every property: drop the rule rather than keep a no-op.
            # An 'add' rule with no properties is not a no-op - it is what puts the
            # field on the view in the first place - so it must survive.
            rule._forget()
        customization._apply()
        return True

    @api.model
    def remove_field_rule(self, model, view_id, view_type, field_name):
        """ Forget a field entirely: its properties, and its place on the view. """
        customization = self._get_or_create(model, view_id, view_type)
        sub_field, sub_view_type, field_name = self._split_key(field_name)
        customization.rule_ids.filtered(
            lambda r: r.field_name == field_name and (r.sub_field or '') == sub_field
            and (r.sub_view_type or False) == sub_view_type)._forget()
        customization._apply()
        return True

    @api.model
    def save_actions(self, model, view_id, view_type, values):
        customization = self._get_or_create(model, view_id, view_type)
        customization.write({name: values[name] for name in values if name in ACTION_FIELDS})
        return True

    @api.model
    def add_field_rule(self, model, view_id, view_type, field_name, anchor_field,
                       position, page_id=None, page_name=None):
        """ Put a field that is not yet in the view next to one that is. """
        customization = self._get_or_create(model, view_id, view_type)
        if field_name not in self.env[model]._fields:
            raise UserError(_("%(model)s has no field called %(field)s.", model=model, field=field_name))
        if customization.rule_ids.filtered(
                lambda r: r.field_name == field_name and not r.sub_field):
            raise UserError(_("%s is already handled by this customization.") % field_name)
        in_page = bool(page_id or page_name)
        self.env['om.pen.rule'].create({
            'customize_id': customization.id,
            'field_name': field_name,
            'kind': 'add',
            'anchor_field': False if in_page else anchor_field,
            'anchor_page_id': page_id or False,
            'anchor_page_name': page_name or '',
            'position': position or 'after',
        })
        customization._apply()
        return True

    @api.model
    def add_subview_field_rule(self, model, view_id, view_type, sub_field, sub_view_type,
                               field_name):
        """ Add a field to the list or form embedded in an x2many on this view. """
        customization = self._get_or_create(model, view_id, view_type)
        x2many = self.env[model]._fields.get(sub_field)
        if not x2many or not x2many.relational:
            raise UserError(_("%(field)s is not a relational field of %(model)s.", field=sub_field, model=model))
        if field_name not in self.env[x2many.comodel_name]._fields:
            raise UserError(_("%(model)s has no field called %(field)s.",
                              model=x2many.comodel_name, field=field_name))
        if sub_view_type not in ('list', 'form'):
            raise UserError(_("Only the embedded list and form can be customized."))
        if customization.rule_ids.filtered(
                lambda r: r.field_name == field_name and r.sub_field == sub_field
                and r.sub_view_type == sub_view_type):
            raise UserError(_("%s is already on that embedded view.") % field_name)

        self.env['om.pen.rule'].create({
            'customize_id': customization.id,
            'field_name': field_name,
            'kind': 'add',
            'sub_field': sub_field,
            'sub_view_type': sub_view_type,
        })
        customization._apply()
        return True

    @api.model
    def subview_targets(self, model, view_id, view_type):
        """ The x2many fields of this view that carry an embedded list or form.

        Only inline views can be customized here: an x2many pointing at a standalone
        view is customized by opening that view itself.
        """
        self._check_customizer()
        customization = self.search([('view_id', '=', view_id)], limit=1)
        view = customization.view_id or self.env['ir.ui.view'].browse(view_id)
        arch = view._get_combined_arch()
        targets = []
        for node in arch.xpath('//field'):
            name = node.get('name')
            field = self.env[model]._fields.get(name)
            if not field or not field.relational:
                continue
            embedded = [child.tag for child in node if child.tag in ('list', 'form')]
            if embedded:
                targets.append({
                    'name': name,
                    'string': field.string,
                    'comodel': field.comodel_name,
                    'views': sorted(set(embedded)),
                })
        return targets

    @api.model
    def move_field_rule(self, model, view_id, view_type, field_name, anchor_field,
                        position, page_name=None):
        """ Put a field that is already on the view somewhere else on it. """
        customization = self._get_or_create(model, view_id, view_type)
        if field_name == anchor_field:
            raise UserError(_("A field cannot be moved next to itself."))
        rule = customization.rule_ids.filtered(
            lambda r: r.field_name == field_name and not r.sub_field)
        values = {
            'anchor_field': False if page_name else anchor_field,
            'anchor_page_name': page_name or '',
            'position': position or 'after',
        }
        if rule:
            # a field this customization added is re-anchored rather than moved, so its
            # own insertion point stays the single source of truth
            if rule.kind == 'tweak':
                values['kind'] = 'move'
            rule.write(values)
        else:
            self.env['om.pen.rule'].create({
                **values,
                'customize_id': customization.id,
                'field_name': field_name,
                'kind': 'move',
            })
        customization._apply()
        return True

    @api.model
    def add_page(self, model, view_id, view_type, title):
        """ Add a page to the view's notebook. """
        customization = self._get_or_create(model, view_id, view_type)
        Page = self.env['om.pen.page']
        name = Page.name_for(title)
        if customization.page_ids.filtered(lambda p: p.name == name):
            raise UserError(_("This view already has a page called %s.") % title)
        page = Page.create({
            'customize_id': customization.id,
            'name': name,
            'string': title,
        })
        customization._apply()
        return {'id': page.id, 'name': page.name, 'string': page.string}

    @api.model
    def remove_page(self, model, view_id, view_type, page_id):
        customization = self._get_or_create(model, view_id, view_type)
        page = customization.page_ids.filtered(lambda p: p.id == page_id)
        if page.published:
            page.to_remove = True
        else:
            page.unlink()
        customization._apply()
        return True

    @api.model
    def action_recheck(self):
        """ Recompute the broken flag for every customization. """
        self._check_customizer()
        records = self.with_context(active_test=False).search([])
        records.custom_view_id._compute_invalid_locators()
        records._compute_broken()
        return len(records.filtered('broken'))

    @api.model
    def field_types(self):
        return ALLOWED_FIELD_TYPES

    @api.model
    def create_field(self, model, values):
        """ Create a custom field on a model, with the guardrails the ORM does not give.

        ir.model.fields raises a bare KeyError for a stored one2many without an inverse,
        and reports the x_ prefix as an IntegrityError, so both are checked up front.
        """
        self._check_customizer()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only a system administrator can create a new field."))

        related = (values.get('related') or '').strip()
        target = self.related_target(model, related) if related else None
        ttype = target['ttype'] if target else values.get('ttype')
        if ttype not in dict(ALLOWED_FIELD_TYPES):
            raise UserError(_("%s is not a field type this module can create.") % ttype)

        label = (values.get('field_description') or '').strip()
        if not label:
            raise UserError(_("A new field needs a label."))

        name = (values.get('name') or '').strip()
        name = self._clean_field_name(model, name) if name else self._field_name_for(model, label)
        field_values = {
            'name': name,
            'field_description': label,
            'model': model,
            'model_id': self.env['ir.model']._get_id(model),
            'ttype': ttype,
            'state': 'manual',
        }

        if target:
            # a related field is not stored, so it adds no column and deleting it later
            # destroys nothing
            field_values.update({
                'related': related,
                'relation': target['relation'],
                'store': False,
                'readonly': True,
            })
            self.env['ir.model.fields'].sudo().with_context(
                update_custom_fields=True).create(field_values)
            return name

        if ttype in ('many2one', 'many2many'):
            relation = values.get('relation')
            if not relation or relation not in self.env:
                raise UserError(_("Pick an existing model to link to."))
            field_values['relation'] = relation
        if ttype == 'selection':
            options = [line.strip() for line in (values.get('selection') or '').splitlines()
                       if line.strip()]
            if not options:
                raise UserError(_("A selection field needs at least one option."))
            field_values['selection_ids'] = [
                Command.create({'value': 'x_%s' % index, 'name': option, 'sequence': index})
                for index, option in enumerate(options, start=1)
            ]
        if ttype == 'monetary':
            currency = next((fname for fname in ('currency_id', 'x_currency_id')
                             if fname in self.env[model]._fields), None)
            if not currency:
                raise UserError(_(
                    "%s has no currency field, so a Money field cannot be added to it.") % model)
            field_values['currency_field'] = currency

        self.env['ir.model.fields'].sudo().with_context(
            update_custom_fields=True).create(field_values)
        return name

    @api.model
    def related_steps(self, model):
        """ The relational fields of a model, for building a related path one hop at a time. """
        self._check_customizer()
        steps = []
        for name, field in self.env[model]._fields.items():
            if field.relational and field.comodel_name in self.env:
                steps.append({
                    'name': name,
                    'string': field.string,
                    'comodel': field.comodel_name,
                })
        return sorted(steps, key=lambda step: step['string'])

    @api.model
    def related_target(self, model, path):
        """ Resolve a dotted path and describe the field it lands on.

        Every hop but the last has to be relational, and Odoo additionally refuses a
        related path through a field it cannot search.
        """
        self._check_customizer()
        parts = [part for part in (path or '').split('.') if part]
        if len(parts) < 2:
            raise UserError(_("A related field needs at least one hop, such as"
                              " partner_id.country_id."))
        current = self.env[model]
        for name in parts[:-1]:
            field = current._fields.get(name)
            if not field or not field.relational:
                raise UserError(_("%s is not a link to another record.") % name)
            # Odoo refuses a related path through a field it cannot search; the flag it
            # uses is _description_searchable, not a public `searchable` attribute
            if not field._description_searchable:
                raise UserError(_(
                    "%s cannot be used in a related path because it is not searchable."
                ) % name)
            current = self.env[field.comodel_name]
        field = current._fields.get(parts[-1])
        if not field:
            raise UserError(_("%(model)s has no field called %(name)s.",
                              model=current._name, name=parts[-1]))
        if field.type not in dict(ALLOWED_FIELD_TYPES):
            raise UserError(_("A %s field cannot be mirrored.") % field.type)
        return {
            'ttype': field.type,
            'relation': field.comodel_name or False,
            'string': field.string,
        }

    @api.model
    def _clean_field_name(self, model, name):
        """ Make a user supplied technical name safe, or say why it cannot be.

        Postgres identifiers are limited to 63 characters and a custom field has to
        start with x_, which is enforced by a CHECK constraint whose error is unhelpful.
        """
        name = re.sub(r'[^a-z0-9_]+', '_', name.strip().lower())
        # strip the prefix before cleaning, so "x_" on its own is recognised as empty
        if name.startswith('x_'):
            name = name[2:]
        name = name.strip('_')
        if not name:
            raise UserError(_("A technical name needs more than the x_ prefix."))
        name = 'x_%s' % name
        if len(name) > 63:
            raise UserError(_(
                "The technical name %s is longer than the 63 characters Postgres allows."
            ) % name)
        if name in self.env[model]._fields:
            raise UserError(_("%(model)s already has a field called %(name)s.",
                              model=model, name=name))
        return name

    @api.model
    def _field_name_for(self, model, label):
        """ A readable x_ name that is free on the model. """
        slug = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_') or 'field'
        candidate = 'x_%s' % slug[:50]
        existing = self.env[model]._fields
        if candidate not in existing:
            return candidate
        for suffix in range(2, 100):
            if (numbered := '%s_%s' % (candidate, suffix)) not in existing:
                return numbered
        raise UserError(_("Could not find a free name for %s.") % label)

    @api.model
    def publish(self, model, view_id, view_type):
        customization = self._get_or_create(model, view_id, view_type)
        if not customization.has_draft:
            raise UserError(_("There is nothing waiting to be published."))
        if customization.draft_invalid:
            raise UserError(_(
                "These changes no longer fit the standard view, usually because a module"
                " was updated. Discard them and make them again."))
        customization.action_publish()
        return True

    @api.model
    def discard_draft(self, model, view_id, view_type):
        customization = self._get_or_create(model, view_id, view_type)
        customization.action_discard_draft()
        return True

    @api.model
    def reset_view(self, view_id):
        self._check_customizer()
        self.search([('view_id', '=', view_id)]).action_reset()
        return True

    @api.model
    def _check_customizer(self):
        if not self.env.user.has_group('om_pen.group_customizer'):
            raise UserError(_("You are not allowed to customize views."))
