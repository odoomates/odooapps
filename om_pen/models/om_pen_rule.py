import ast

from lxml import etree

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

# '' leaves the attribute alone, '0'/'1' force it, anything else is a python
# expression evaluated by the client against the record
TRISTATE_HELP = "Leave empty to keep the standard behaviour, 1 to force it on, 0 to" \
                " force it off, or a python expression such as state != 'draft'."

# many2x widget options, as the web client names them
RELATIONAL_OPTIONS = {
    'opt_no_open': 'no_open',
    'opt_no_create': 'no_create',
    'opt_no_quick_create': 'no_quick_create',
    'opt_no_create_edit': 'no_create_edit',
}


class OmPenRule(models.Model):
    _name = 'om.pen.rule'
    _description = "View Customization Rule"
    _order = 'sequence, id'

    customize_id = fields.Many2one('om.pen.view', string="Customization",
                                   required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    field_name = fields.Char(string="Field", required=True)
    kind = fields.Selection(
        [('tweak', "Customize an existing field"),
         ('add', "Add a field to the view"),
         ('move', "Move a field already on the view")],
        default='tweak', required=True)
    anchor_field = fields.Char(
        string="Placed Next To",
        help="Technical name of the field this one is inserted next to. Anchoring on a"
             " field rather than on a position keeps working when the standard view"
             " moves things around.")
    position = fields.Selection(
        [('after', "After"), ('before', "Before")], default='after')
    anchor_page_id = fields.Many2one(
        'om.pen.page', string="Placed In Page", ondelete='cascade',
        help="Put the field inside a page this customization added, instead of next to"
             " an existing field.")
    anchor_page_name = fields.Char(
        string="Placed In Existing Page", default='',
        help="Technical name of a page the standard view already has. Only named pages"
             " can be targeted: a page is matched by @name, and the engine forbids"
             " matching on translated attributes such as the page title.")
    sub_field = fields.Char(
        string="Inside x2many", default='',
        help="Technical name of the one2many or many2many whose embedded view this rule"
             " applies to. Empty means the rule applies to the view itself.")
    sub_view_type = fields.Selection(
        [('list', "List"), ('form', "Form")], string="Embedded View", default=False,
        help="Which of the embedded views of that x2many the rule applies to.")
    group_ids = fields.Many2many(
        'res.groups', 'om_pen_rule_group_rel', 'rule_id', 'group_id',
        string="Visible To",
        help="Leave empty to show the field to everyone. Otherwise only these groups"
             " see it; the server strips it from the view for anybody else.")

    label = fields.Char(string="Label", help="Replaces the label shown on this view only.")
    label_scope = fields.Json(
        string="Renamed Occurrences",
        help="Which occurrences of the field, and of its <label for=...> nodes, the new"
             " label applies to, as 1-based positions: {'field': [...], 'label': [...]}."
             " Empty means all of them. Set from the caption the user saw, so renaming"
             " one of two different captions leaves the other alone.")
    help_text = fields.Char(string="Tooltip")
    widget = fields.Char(string="Widget")
    placeholder = fields.Char(string="Placeholder")
    optional = fields.Selection(
        [('show', "Shown by default"), ('hide', "Hidden by default")],
        string="Optional Column",
        help="List views only. An optional column can be switched on and off by each"
             " user from the column picker.")

    invisible = fields.Char(string="Invisible", help=TRISTATE_HELP)
    readonly = fields.Char(string="Readonly", help=TRISTATE_HELP)
    required = fields.Char(string="Required", help=TRISTATE_HELP)
    column_invisible = fields.Char(string="Column Invisible", help=TRISTATE_HELP)

    opt_no_open = fields.Boolean(string="Forbid Opening")
    opt_no_create = fields.Boolean(string="Forbid Creating")
    opt_no_quick_create = fields.Boolean(string="Forbid Quick Create")
    opt_no_create_edit = fields.Boolean(string="Forbid Create & Edit")
    base_options = fields.Char(
        string="Original Options", default='{}',
        help="The options already carried by the field in the view. The customized"
             " options are merged on top of these, because options travel as one"
             " attribute and a partial value would drop the rest.")

    condition_data = fields.Json(
        string="Conditions", default=dict,
        help="How each condition was built in the panel, so it can be shown as rows"
             " again instead of raw python. The expression itself stays in the"
             " modifier: a hand written one simply has no entry here.")
    published_values = fields.Json(
        string="Published State", default=dict,
        help="What this rule looked like the last time it was published. The live view"
             " is rendered from this, never from the fields above, so editing a rule"
             " cannot change what other users see until it is published.")
    to_remove = fields.Boolean(
        string="Removed On Publish",
        help="The rule still applies until the next publish, which deletes it.")

    # an index, not a table constraint: a UNIQUE constraint cannot hold the
    # COALESCE expressions that make an empty sub-view count as one value
    _field_uniq = models.UniqueIndex(
        "(customize_id, field_name, COALESCE(sub_field, ''),"
        " COALESCE(sub_view_type, ''))",
        "A field can only be customized once per view.",
    )

    @api.constrains('base_options')
    def _check_base_options(self):
        for rule in self:
            try:
                value = ast.literal_eval(rule.base_options or '{}')
            except (ValueError, SyntaxError) as error:
                raise ValidationError(_("The original options of %s are not valid.") % rule.field_name) from error
            if not isinstance(value, dict):
                raise ValidationError(_("The original options of %s must be a dictionary.") % rule.field_name)

    # the shape of a rule as it gets published; everything the arch is built from
    SNAPSHOT_FIELDS = (
        'field_name', 'kind', 'label', 'help_text', 'widget', 'placeholder', 'optional',
        'invisible', 'readonly', 'required', 'column_invisible',
        'opt_no_open', 'opt_no_create', 'opt_no_quick_create', 'opt_no_create_edit',
        'base_options', 'anchor_field', 'anchor_page_name', 'position',
        'sub_field', 'sub_view_type', 'condition_data', 'label_scope',
    )

    def _snapshot(self):
        """ The publishable state of this rule, as plain JSON. """
        self.ensure_one()
        values = {name: self[name] for name in self.SNAPSHOT_FIELDS}
        values['group_ids'] = sorted(self.group_ids.ids)
        values['anchor_page_id'] = self.anchor_page_id.id or False
        return values

    def _published(self):
        """ An in-memory copy of this rule as it was last published.

        Rendering the live view from this, rather than from the record's own fields, is
        what makes an unpublished edit invisible to everybody.
        """
        self.ensure_one()
        values = dict(self.published_values or {})
        if not values:
            return self.browse()
        values['group_ids'] = [Command.set(values.get('group_ids') or [])]
        values['customize_id'] = self.customize_id.id
        return self.new(values)

    def _is_draft(self):
        self.ensure_one()
        if self.to_remove:
            return True
        return self._snapshot() != (self.published_values or {})

    def _forget(self):
        """ Drop the rule, or mark it to be dropped by the next publish.

        A rule that is already live cannot simply vanish: the live view is built from
        published state, and removing it now would publish the removal by surprise.
        """
        self.filtered(lambda r: r.published_values).to_remove = True
        self.filtered(lambda r: not r.published_values).unlink()

    def _attribute_values(self):
        """ Return the attributes this rule sets on its field node.

        A value of None means "remove the attribute", which is how a field hidden
        upstream is brought back: an empty <attribute> deletes it.
        """
        self.ensure_one()
        values = {}
        for attribute, value in (
            ('string', self.label),
            ('help', self.help_text),
            ('widget', self.widget),
            ('placeholder', self.placeholder),
            ('optional', self.optional),
            ('invisible', self.invisible),
            ('readonly', self.readonly),
            ('required', self.required),
            ('column_invisible', self.column_invisible),
        ):
            if value:
                values[attribute] = value

        if options := self._options():
            values['options'] = options
        if groups := self._groups_attribute():
            values['groups'] = groups
        return values

    def _groups_attribute(self):
        """ The groups= attribute, as a comma separated list of external ids.

        Group visibility has to be done here rather than on ir.model.fields, whose
        `groups` column is an unimplemented leftover with an empty table.
        """
        self.ensure_one()
        external_ids = []
        for group in self.group_ids:
            if external_id := group.get_external_id().get(group.id):
                external_ids.append(external_id)
            else:
                raise ValidationError(_(
                    "The group %s has no external id, so it cannot be used to hide a"
                    " field in a view.") % group.display_name)
        return ','.join(external_ids)

    def _options(self):
        """ Merge the customized many2x options over the ones already in the view. """
        self.ensure_one()
        wanted = {name: True for field, name in RELATIONAL_OPTIONS.items() if self[field]}
        if not wanted:
            return None
        options = ast.literal_eval(self.base_options or '{}')
        options.update(wanted)
        return repr(options)

    def _render_nodes(self, arch):
        if self.kind == 'add':
            return self._render_add_nodes(arch)
        # a moved field can also carry its own tweaks, so both sets of specs are needed
        specs = self._render_move_nodes(arch) if self.kind == 'move' else []
        return specs + self._render_tweak_nodes(arch)

    def _render_move_nodes(self, arch):
        """ Lift the field out of where the standard view puts it and re-insert it.

        `position="move"` on a child of the spec is the inheritance engine's own way of
        relocating an existing node, so the field keeps every attribute it already had.
        """
        self.ensure_one()
        if page := self._page_path(arch):
            # moving into a page rather than next to a field: same extraction, different
            # destination
            if not arch.xpath("//field[@name=$name]", name=self.field_name):
                raise ValidationError(_(
                    "%s is not in this view any more, so the move cannot be applied."
                ) % self.field_name)
            spec = etree.Element('xpath', expr=page, position='inside')
            etree.SubElement(spec, 'field', name=self.field_name, position='move')
            return [spec]
        if not self.anchor_field:
            raise ValidationError(_("%s has nowhere to move to.") % self.field_name)
        if self.anchor_field == self.field_name:
            raise ValidationError(_("%s cannot be moved next to itself.") % self.field_name)
        for name in (self.field_name, self.anchor_field):
            if not arch.xpath("//field[@name=$name]", name=name):
                raise ValidationError(_(
                    "%s is not in this view any more, so the move cannot be applied.") % name)

        spec = etree.Element('field', name=self.anchor_field, position=self.position or 'after')
        etree.SubElement(spec, 'field', name=self.field_name, position='move')
        return [spec]

    def _sub_view_path(self, arch):
        """ The xpath prefix of the embedded view this rule lives in, if any. """
        self.ensure_one()
        if not self.sub_field:
            return ''
        path = "//field[@name='%s']/%s" % (self.sub_field, self.sub_view_type or 'list')
        if not arch.xpath(path):
            raise ValidationError(_(
                "%(field)s has no embedded %(kind)s view in this view, so a field cannot"
                " be added to it here. Customize the %(kind)s view of the linked model"
                " instead.",
                field=self.sub_field, kind=self.sub_view_type or 'list',
            ))
        return path

    def _page_path(self, arch):
        """ The xpath of the page this rule drops into, if any. """
        self.ensure_one()
        name = self.anchor_page_id.name or self.anchor_page_name
        if not name:
            return ''
        path = "//page[@name='%s']" % name
        if not self.anchor_page_id and not arch.xpath(path):
            raise ValidationError(_(
                "This view has no page called %s any more.") % name)
        return path

    def _render_add_nodes(self, arch):
        """ Insert the field where the user put it, carrying its own attributes inline. """
        self.ensure_one()
        container = self._sub_view_path(arch) or self._page_path(arch)
        if container:
            spec = etree.Element('xpath', expr=container, position='inside')
            added = etree.SubElement(spec, 'field', name=self.field_name)
            for attribute, value in self._attribute_values().items():
                added.set(attribute, value)
            return [spec]

        if not self.anchor_field:
            raise ValidationError(
                _("%s has nothing to be placed next to.") % self.field_name)
        # the anchor may itself be a field this customization adds: the user drops the
        # next field beside the one they just placed. Rules render in creation order, so
        # that field is in the view by the time this spec is applied.
        added_here = self.customize_id.rule_ids.filtered(
            lambda r: r.kind == 'add' and r.field_name == self.anchor_field and not r.sub_field)
        if not added_here and not arch.xpath("//field[@name=$name]", name=self.anchor_field):
            raise ValidationError(_(
                "%(field)s cannot be placed next to %(anchor)s, which is not in this view.",
                field=self.field_name, anchor=self.anchor_field))

        spec = etree.Element('field', name=self.anchor_field, position=self.position or 'after')
        added = etree.SubElement(spec, 'field', name=self.field_name)
        for attribute, value in self._attribute_values().items():
            added.set(attribute, value)
        return [spec]

    def _render_tweak_nodes(self, arch):
        """ Return the inheritance specs for this rule.

        :param arch: the combined arch of the view being customized, used to count how
            many times the field and its labels appear.

        Two things make this more than a single spec:

        - a field can appear several times in one view (sale.order shows date_order
          twice, under different conditions), and a <field name="..."> spec only ever
          matches the first one, so every occurrence past the first needs a positional
          xpath;
        - a field rendered with nolabel="1" next to an explicit <label for="..."/> takes
          its caption from that label, not from the field's own string, so renaming has
          to reach the label too.
        """
        self.ensure_one()
        values = self._attribute_values()
        if not values:
            return []

        if prefix := self._sub_view_path(arch):
            # a field of an embedded view is addressed through its container, otherwise
            # the spec would match the same name on the main view instead
            spec = etree.Element(
                'xpath', expr="%s/field[@name='%s']" % (prefix, self.field_name),
                position='attributes')
            specs = [self._fill(spec, values)]
            return specs

        scope = self.label_scope or {}
        field_scope = scope.get('field')
        label_scope = scope.get('label')
        specs = []
        locators = self._locators("field[@name='%s']" % self.field_name, arch,
                                  "//field[@name=$name]")
        for index, spec in enumerate(locators, 1):
            own = values
            if len(locators) > 1 and field_scope is not None and index not in field_scope:
                # another caption of the same field: everything but the rename
                own = {name: value for name, value in values.items() if name != 'string'}
            if own:
                specs.append(self._fill(spec, own))
        if self.label:
            for index, spec in enumerate(
                    self._locators("label[@for='%s']" % self.field_name, arch,
                                   "//label[@for=$name]"), 1):
                if label_scope is None or index in label_scope:
                    specs.append(self._fill(spec, {'string': self.label}))
        return specs

    def _label_scope_for(self, arch, caption):
        """ The occurrences that show `caption`, or None when that cannot be told.

        A field can be on a view more than once, and its <label for=...> nodes can each
        carry their own caption: sale.order shows Order Date and, elsewhere, Quotation
        Date for the same field. Renaming the one the user clicked must leave the other
        alone. The screen only says which caption was clicked, not which node, because
        invisible nodes are never rendered; the caption is enough to find the nodes.

        :param arch: the combined arch of the view, in the user's language, so its
            captions compare with what the user read on screen
        :return: {'field': [...], 'label': [...]} of 1-based positions, or None when
            every occurrence shows that caption or none of them does
        """
        self.ensure_one()
        caption = (caption or '').strip()
        model = self.env.get(self.customize_id.model)
        if not caption or model is None or self.field_name not in model._fields:
            return None
        default = model._fields[self.field_name]._description_string(self.env)
        fields_ = arch.xpath('//field[@name=$name]', name=self.field_name)
        labels = arch.xpath('//label[@for=$name]', name=self.field_name)
        field_captions = [node.get('string') or default for node in fields_]
        label_captions = [node.get('string') or (node.text or '').strip() or default
                          for node in labels]
        captions = field_captions + label_captions
        if caption not in captions or len(set(captions)) <= 1:
            return None
        return {
            'field': [i for i, text in enumerate(field_captions, 1) if text == caption],
            'label': [i for i, text in enumerate(label_captions, 1) if text == caption],
        }

    def _locators(self, path, arch, count_xpath):
        """ One spec per occurrence of the node in the view.

        A single occurrence keeps the plain <field name="..."> form, which the
        inheritance engine matches at any depth and which therefore survives the
        upstream view moving the field around. Positional xpaths are only used when
        there is genuinely more than one node to tell apart.
        """
        self.ensure_one()
        count = len(arch.xpath(count_xpath, name=self.field_name))
        if count <= 1 and path.startswith('field['):
            return [etree.Element('field', name=self.field_name, position='attributes')]
        return [
            etree.Element('xpath', expr="(//%s)[%d]" % (path, index), position='attributes')
            for index in range(1, count + 1)
        ]

    @staticmethod
    def _fill(spec, values):
        for attribute, value in values.items():
            element = etree.SubElement(spec, 'attribute', name=attribute)
            element.text = value
        return spec
