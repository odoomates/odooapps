import ast
import base64
import io
import zipfile

from lxml import etree

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


class PublishMixin:
    """ Changes are drafts until published, so a test that asserts on the rendered view
    has to publish first. """

    def _publish(self, view=None):
        # several tests build their own view, so with no argument this publishes every
        # customization that has something waiting
        domain = [('view_id', '=', view.id)] if view else []
        for customization in self.env['om.pen.view'].search(domain):
            if customization.has_draft:
                customization.action_publish()


@tagged('post_install', '-at_install')
class TestArchGeneration(PublishMixin, TransactionCase):
    """ The generated arch is what every feature of this module reduces to, so it is
    asserted directly rather than through the rendered view. """

    def setUp(self):
        super().setUp()
        self.view = self.env.ref('base.view_partner_form')
        self.customization = self.env['om.pen.view'].with_context(
            om_pen_skip_apply=True).create({
                'model': 'res.partner',
                'view_id': self.view.id,
                'view_type': 'form',
            })

    def _rule(self, **values):
        return self.env['om.pen.rule'].create({
            'customize_id': self.customization.id,
            'field_name': 'phone',
            **values,
        })

    def test_a_rule_that_changes_nothing_produces_no_spec(self):
        self._rule()
        self.assertEqual(self.customization._render_arch(draft=True), '<data/>',
                         "an empty rule must not emit an inheritance spec")

    def test_the_label_is_changed_by_an_attribute_spec(self):
        __, customization = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'function', 'label': "Direct Line"})

        arch = etree.fromstring(customization._render_arch(draft=True))
        spec = arch[0]
        self.assertEqual(spec.get('position'), 'attributes')
        self.assertEqual(spec[0].get('name'), 'string')
        self.assertEqual(spec[0].text, "Direct Line")

    def test_a_field_is_hidden_and_brought_back(self):
        """ An empty <attribute> deletes the attribute, which is the only way to undo a
        field that the standard view hides. """
        rule = self._rule(invisible='1')
        arch = etree.fromstring(self.customization._render_arch(draft=True))
        self.assertEqual(arch[0][0].text, '1', "1 forces the field hidden")

        rule.invisible = '0'
        arch = etree.fromstring(self.customization._render_arch(draft=True))
        self.assertEqual(arch[0][0].text, '0',
                         "0 must be emitted rather than dropped, so it also overrides a"
                         " field that is readonly or invisible in python")

    def test_a_condition_is_passed_through_untouched(self):
        self._rule(readonly="state != 'draft'")
        arch = etree.fromstring(self.customization._render_arch(draft=True))
        self.assertEqual(arch[0][0].text, "state != 'draft'",
                         "the expression is evaluated by the client, we must not quote it")

    def test_relational_options_are_merged_over_the_existing_ones(self):
        """ options travels as one attribute, so writing only the new keys would drop
        whatever the standard view already set. """
        self._rule(field_name='parent_id', base_options="{'no_quick_create': True}",
                   opt_no_open=True)
        arch = etree.fromstring(self.customization._render_arch(draft=True))
        options = ast.literal_eval(arch[0][0].text)
        self.assertEqual(options, {'no_quick_create': True, 'no_open': True},
                         "the original options must survive the merge")

    def test_disabled_actions_land_on_the_root_tag(self):
        self.customization.with_context(om_pen_skip_apply=True).write({
            'create_ok': False, 'duplicate_ok': False})
        arch = etree.fromstring(self.customization._render_arch(draft=True))
        spec = arch[0]
        self.assertEqual(spec.tag, 'xpath')
        self.assertEqual(spec.get('expr'), '//form', "the root tag carries the action attributes")
        self.assertEqual({child.get('name'): child.text for child in spec},
                         {'create': '0', 'duplicate': '0'})

    def test_export_and_import_are_only_emitted_for_lists(self):
        """ They are list-only attributes; on a form they would be dead weight. """
        self.customization.with_context(om_pen_skip_apply=True).write({'export_ok': False})
        self.assertEqual(self.customization._render_arch(draft=True), '<data/>',
                         "a form view must not receive export_xlsx")

        self.customization.with_context(om_pen_skip_apply=True).view_type = 'list'
        arch = etree.fromstring(self.customization._render_arch(draft=True))
        self.assertEqual(arch[0].get('expr'), '//list',
                         "there is no <tree> tag: an xpath on //tree would never locate")

    def test_applying_creates_an_extension_view_that_odoo_accepts(self):
        self._rule(label="Direct Line")
        self.customization.action_publish()
        custom = self.customization.custom_view_id
        self.assertTrue(custom, "a customization with rules must produce a view")
        self.assertEqual(custom.inherit_id, self.view)
        self.assertEqual(custom.mode, 'extension')
        self.assertEqual(custom.priority, 9999, "it must apply after every other extension")
        self.assertTrue(custom.xml_id.startswith('__custom__.'),
                        "the generated view needs an external id, filed under a module"
                        " that is never installed so no upgrade can delete it")
        arch = self.env['res.partner'].get_view(self.view.id, 'form')['arch']
        self.assertIn('Direct Line', arch, "the change must reach the rendered view")

    def _view_with(self, arch):
        view = self.env['ir.ui.view'].create({
            'name': "partner test form",
            'model': 'res.partner',
            'arch': arch,
        })
        return view, self.env['om.pen.view'].with_context(
            om_pen_skip_apply=True).create({
                'model': 'res.partner',
                'view_id': view.id,
                'view_type': 'form',
            })

    def test_a_field_shown_twice_is_customized_in_both_places(self):
        """ sale.order renders date_order twice under different conditions, and a plain
        <field name="..."> spec only ever matches the first one. """
        __, customization = self._view_with("""
            <form>
                <field name="function" invisible="not active"/>
                <field name="function" invisible="active"/>
            </form>
        """)
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'function', 'readonly': '1'})

        arch = etree.fromstring(customization._render_arch(draft=True))
        self.assertEqual([spec.get('expr') for spec in arch],
                         ["(//field[@name='function'])[1]", "(//field[@name='function'])[2]"],
                         "both occurrences must be reached")
        customization.action_publish()
        rendered = self.env['res.partner'].get_view(customization.view_id.id, 'form')['arch']
        self.assertEqual(rendered.count('readonly="1"'), 2,
                         "the customization must survive Odoo's own view combination")

    def test_an_explicit_label_is_renamed_too(self):
        """ A field with nolabel="1" takes its caption from a sibling <label for="..."/>,
        so changing the field's own string would rename nothing on screen. """
        __, customization = self._view_with("""
            <form>
                <label for="function" string="Job Position"/>
                <field name="function" nolabel="1"/>
            </form>
        """)
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'function', 'label': "Role"})

        customization.action_publish()
        rendered = self.env['res.partner'].get_view(customization.view_id.id, 'form')['arch']
        self.assertIn('string="Role"', rendered, "the label node must carry the new caption")
        self.assertNotIn("Job Position", rendered, "the old caption must be gone")

    def test_a_single_occurrence_keeps_the_robust_locator(self):
        """ A plain <field name="..."> spec matches at any depth, so it survives the
        upstream view moving the field; a positional xpath would not. """
        __, customization = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'function', 'readonly': '1'})

        arch = etree.fromstring(customization._render_arch(draft=True))
        self.assertEqual(arch[0].tag, 'field',
                         "one occurrence must not be turned into a positional xpath")
        self.assertEqual(arch[0].get('name'), 'function')

    def test_a_field_can_be_added_next_to_another(self):
        view, customization = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.view'].add_field_rule(
            'res.partner', view.id, 'form', 'website', 'function', 'after')
        self._publish()

        rendered = self.env['res.partner'].get_view(view.id, 'form')['arch']
        self.assertIn('name="website"', rendered, "the added field must reach the view")
        self.assertLess(rendered.index('name="function"'), rendered.index('name="website"'),
                        "it must land after its anchor")

    def test_applying_empty_properties_does_not_remove_an_added_field(self):
        """ After placing a field the panel selects it, so pressing Apply with nothing
        filled in used to delete the rule that put the field on the view. """
        view, __ = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.view'].add_field_rule(
            'res.partner', view.id, 'form', 'website', 'function', 'after')
        self._publish()

        self.env['om.pen.view'].save_field_rule(
            'res.partner', view.id, 'form', 'website',
            {'label': '', 'invisible': '', 'readonly': '', 'required': ''})
        self._publish()

        rendered = self.env['res.partner'].get_view(view.id, 'form')['arch']
        self.assertIn('name="website"', rendered,
                      "an add rule with no properties is not a no-op, it is the field")

    def test_applying_empty_properties_drops_a_tweak_rule(self):
        """ The same call on a rule that only tweaks an existing field should still
        clean it up, otherwise no-op rules pile up forever. """
        view, customization = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.view'].save_field_rule(
            'res.partner', view.id, 'form', 'function', {'label': "Role"})
        self._publish()
        self.assertTrue(customization.rule_ids)

        self.env['om.pen.view'].save_field_rule(
            'res.partner', view.id, 'form', 'function', {'label': ''})
        self._publish()
        self.assertFalse(customization.rule_ids, "an emptied tweak rule must be dropped")

    def test_a_field_can_be_removed_from_the_view_again(self):
        view, customization = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.view'].add_field_rule(
            'res.partner', view.id, 'form', 'website', 'function', 'after')
        self._publish()

        self.env['om.pen.view'].remove_field_rule('res.partner', view.id, 'form', 'website')
        self._publish()
        rendered = self.env['res.partner'].get_view(view.id, 'form')['arch']
        self.assertNotIn('name="website"', rendered, "removing must take it off the view")
        self.assertFalse(customization.custom_view_id,
                         "nothing is customized any more, so no view should be left behind")

    def test_adding_a_field_twice_is_refused(self):
        view, __ = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.view'].add_field_rule(
            'res.partner', view.id, 'form', 'website', 'function', 'after')
        self._publish()
        with self.assertRaises(UserError, msg="a second rule would emit a duplicate field"):
            self.env['om.pen.view'].add_field_rule(
                'res.partner', view.id, 'form', 'website', 'function', 'after')
            self._publish()

    def test_an_added_field_needs_an_anchor_that_exists(self):
        """ Without this the arch is written and only fails later, during a module
        upgrade, which is exactly the failure mode this module exists to avoid. """
        view, customization = self._view_with('<form><field name="function"/></form>')
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'website',
            'kind': 'add', 'anchor_field': 'comment'})
        with self.assertRaises(ValidationError, msg="a missing anchor must be refused"):
            customization._render_arch(draft=True)

    def test_a_new_field_is_created_with_an_x_name(self):
        name = self.env['om.pen.view'].create_field('res.partner', {
            'field_description': "Internal Reference", 'ttype': 'char'})
        self.assertEqual(name, 'x_internal_reference',
                         "the label becomes a readable technical name")
        field = self.env['res.partner']._fields[name]
        self.assertEqual(field.string, "Internal Reference")
        self.assertTrue(field.manual, "it must be a custom field")

    def test_a_field_type_outside_the_whitelist_is_refused(self):
        """ properties and many2one_reference are not handled by _instanciate_attrs and
        would be created broken. """
        with self.assertRaises(UserError, msg="the type must be refused up front"):
            self.env['om.pen.view'].create_field('res.partner', {
                'field_description': "Nope", 'ttype': 'properties'})

    def test_a_relational_field_needs_a_real_model(self):
        with self.assertRaises(UserError, msg="a bad comodel must be caught before create"):
            self.env['om.pen.view'].create_field('res.partner', {
                'field_description': "Linked", 'ttype': 'many2one', 'relation': 'not.a.model'})

    def test_clearing_the_rules_removes_the_generated_view(self):
        rule = self._rule(label="Direct Line")
        self.customization.action_publish()
        self.assertTrue(self.customization.custom_view_id)

        rule.unlink()
        self.customization.action_publish()
        self.assertFalse(self.customization.custom_view_id,
                         "an empty customization must leave no view behind to break upgrades")


@tagged('post_install', '-at_install')
class TestExport(PublishMixin, TransactionCase):
    """ The export is what makes a customization portable, so the produced module has to
    be a real one: valid XML, the right dependencies, and fields carried with it. """

    def setUp(self):
        super().setUp()
        self.view = self.env['ir.ui.view'].create({
            'name': "partner export form",
            'model': 'res.partner',
            'arch': '<form><field name="function"/></form>',
        })
        self.env['ir.model.data'].create({
            'module': '__export_test__', 'name': 'partner_export_form',
            'model': 'ir.ui.view', 'res_id': self.view.id,
        })
        self.customization = self.env['om.pen.view'].with_context(
            om_pen_skip_apply=True).create({
                'model': 'res.partner',
                'view_id': self.view.id,
                'view_type': 'form',
            })

    def _zip(self):
        action = self.customization.action_export_module()
        attachment = self.env['ir.attachment'].browse(
            int(action['url'].split('/web/content/')[1].split('?')[0]))
        return zipfile.ZipFile(io.BytesIO(base64.b64decode(attachment.datas)))

    def test_the_exported_module_is_a_real_module(self):
        self.env['om.pen.rule'].create({
            'customize_id': self.customization.id, 'field_name': 'function', 'label': "Role"})
        self.customization.action_publish()

        archive = self._zip()
        names = archive.namelist()
        for expected in ('om_pen_export/__manifest__.py',
                         'om_pen_export/__init__.py',
                         'om_pen_export/views/customizations.xml',
                         'om_pen_export/data/ir_model_fields.xml'):
            self.assertIn(expected, names, "an installable module needs %s" % expected)

        manifest = ast.literal_eval(
            archive.read('om_pen_export/__manifest__.py').decode())
        self.assertIn('__export_test__', manifest['depends'],
                      "the module owning the customized view must be a dependency")

        views = etree.fromstring(archive.read('om_pen_export/views/customizations.xml'))
        record = views.find('.//record[@model="ir.ui.view"]')
        self.assertEqual(record.find('field[@name="inherit_id"]').get('ref'),
                         '__export_test__.partner_export_form',
                         "the inherited view is referenced by external id, not by database id")
        self.assertIsNotNone(record.find('field[@name="arch"]/data'),
                             "the generated arch must travel with it")

    def test_a_custom_field_is_exported_with_the_view_that_uses_it(self):
        name = self.env['om.pen.view'].create_field('res.partner', {
            'field_description': "Export Me", 'ttype': 'char'})
        self.env['om.pen.view'].add_field_rule(
            'res.partner', self.view.id, 'form', name, 'function', 'after')
        self._publish()

        fields_doc = etree.fromstring(
            self._zip().read('om_pen_export/data/ir_model_fields.xml'))
        record = fields_doc.find('.//record[@model="ir.model.fields"]')
        self.assertEqual(record.find('field[@name="name"]').text, name)
        self.assertEqual(record.find('field[@name="state"]').text, 'manual',
                         "it has to land as a custom field on the target database")
        self.assertEqual(record.find('field[@name="model_id"]').get('ref'),
                         'base.model_res_partner',
                         "the model is referenced by external id so the id can differ")

    def test_exporting_a_view_with_no_external_id_is_refused(self):
        """ A database id means nothing on another database, so a view we cannot name
        must stop the export rather than produce a module that installs wrongly. """
        orphan_view = self.env['ir.ui.view'].create({
            'name': "no xmlid", 'model': 'res.partner',
            'arch': '<form><field name="function"/></form>',
        })
        customization = self.env['om.pen.view'].with_context(
            om_pen_skip_apply=True).create({
                'model': 'res.partner', 'view_id': orphan_view.id, 'view_type': 'form'})
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'function', 'label': "X"})
        customization.action_publish()

        with self.assertRaises(UserError, msg="an unnameable view must stop the export"):
            customization.action_export_module()


@tagged('post_install', '-at_install')
class TestPagesAndGroups(PublishMixin, TransactionCase):

    def setUp(self):
        super().setUp()
        self.view = self.env['ir.ui.view'].create({
            'name': "partner notebook form",
            'model': 'res.partner',
            'arch': '''
                <form>
                    <field name="function"/>
                    <notebook>
                        <page name="first" string="First"/>
                    </notebook>
                </form>
            ''',
        })

    def test_a_page_is_added_to_the_notebook(self):
        page = self.env['om.pen.view'].add_page(
            'res.partner', self.view.id, 'form', "Extra Info")
        self._publish()
        self.assertEqual(page['name'], 'x_extra_info',
                         "the title becomes a readable technical name")

        rendered = self.env['res.partner'].get_view(self.view.id, 'form')['arch']
        self.assertIn('string="Extra Info"', rendered, "the page must reach the view")

    def test_a_field_can_be_dropped_into_an_added_page(self):
        page = self.env['om.pen.view'].add_page(
            'res.partner', self.view.id, 'form', "Extra Info")
        self._publish()
        self.env['om.pen.view'].add_field_rule(
            'res.partner', self.view.id, 'form', 'website', False, 'after', page['id'])
        self._publish()

        arch = etree.fromstring(
            self.env['res.partner'].get_view(self.view.id, 'form')['arch'])
        placed = arch.xpath("//page[@name='x_extra_info']/field[@name='website']")
        self.assertTrue(placed, "the field must land inside the page, not next to it")

    def test_a_page_needs_a_notebook_to_live_in(self):
        """ Saying so beats writing an arch whose xpath silently fails to locate. """
        flat = self.env['ir.ui.view'].create({
            'name': "no notebook", 'model': 'res.partner',
            'arch': '<form><field name="function"/></form>',
        })
        with self.assertRaises(UserError, msg="a view with no notebook must be refused"):
            self.env['om.pen.view'].add_page('res.partner', flat.id, 'form', "Nope")
            self._publish()

    def test_a_field_can_be_restricted_to_groups(self):
        """ Group visibility has to be a view attribute: ir.model.fields.groups is an
        unimplemented leftover with an empty table and does nothing. """
        group = self.env.ref('base.group_system')
        self.env['om.pen.view'].save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'group_ids': [group.id]})
        self._publish()

        customization = self.env['om.pen.view'].search([('view_id', '=', self.view.id)])
        spec = etree.fromstring(customization._render_arch(draft=True))
        self.assertEqual(spec.find('.//attribute[@name="groups"]').text, 'base.group_system',
                         "the spec must name the group by external id")

        outsider = self.env['res.users'].create({
            'name': "Outsider", 'login': 'om_pen_outsider',
            'groups_id': [Command.set(self.env.ref('base.group_user').ids)],
        })
        admin_arch = self.env['res.partner'].get_view(self.view.id, 'form')['arch']
        other_arch = self.env['res.partner'].with_user(outsider).get_view(
            self.view.id, 'form')['arch']
        self.assertIn('name="function"', admin_arch, "a system user still sees it")
        self.assertNotIn('name="function"', other_arch,
                         "the server must strip the field for everybody else")

    def test_a_group_with_no_external_id_is_refused(self):
        group = self.env['res.groups'].create({'name': "Ad Hoc"})
        customization = self.env['om.pen.view'].with_context(
            om_pen_skip_apply=True).create({
                'model': 'res.partner', 'view_id': self.view.id, 'view_type': 'form'})
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'function',
            'group_ids': [Command.set(group.ids)]})

        with self.assertRaises(ValidationError,
                               msg="a group with no xmlid cannot be named in an arch"):
            customization._render_arch(draft=True)


@tagged('post_install', '-at_install')
class TestMove(PublishMixin, TransactionCase):
    """ Moving reuses the inheritance engine's own position="move", so the field keeps
    every attribute the standard view gave it. """

    def setUp(self):
        super().setUp()
        self.view = self.env['ir.ui.view'].create({
            'name': "partner move form",
            'model': 'res.partner',
            'arch': '''
                <form>
                    <field name="function"/>
                    <field name="website"/>
                    <field name="comment"/>
                </form>
            ''',
        })

    def _order(self):
        arch = etree.fromstring(self.env['res.partner'].get_view(self.view.id, 'form')['arch'])
        return [node.get('name') for node in arch.xpath('//field')]

    def test_a_field_can_be_dragged_after_another(self):
        self.assertEqual(self._order(), ['function', 'website', 'comment'])
        self.env['om.pen.view'].move_field_rule(
            'res.partner', self.view.id, 'form', 'function', 'comment', 'after')
        self._publish()
        self.assertEqual(self._order(), ['website', 'comment', 'function'],
                         "the field must leave its old place, not be duplicated")

    def test_a_field_can_be_dragged_before_another(self):
        self.env['om.pen.view'].move_field_rule(
            'res.partner', self.view.id, 'form', 'comment', 'function', 'before')
        self._publish()
        self.assertEqual(self._order(), ['comment', 'function', 'website'])

    def test_a_moved_field_keeps_its_own_tweaks(self):
        """ kind is a single column, so a field that is both moved and renamed has to
        emit both sets of specs from one rule. """
        self.env['om.pen.view'].move_field_rule(
            'res.partner', self.view.id, 'form', 'function', 'comment', 'after')
        self._publish()
        self.env['om.pen.view'].save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})
        self._publish()

        arch = self.env['res.partner'].get_view(self.view.id, 'form')['arch']
        self.assertIn('Role', arch, "the rename must survive the move")
        self.assertEqual(self._order(), ['website', 'comment', 'function'],
                         "and the move must survive the rename")

    def test_moving_a_field_onto_itself_is_refused(self):
        with self.assertRaises(UserError, msg="the engine would lose the node"):
            self.env['om.pen.view'].move_field_rule(
                'res.partner', self.view.id, 'form', 'function', 'function', 'after')
            self._publish()

    def test_re_anchoring_an_added_field_does_not_turn_it_into_a_move(self):
        """ A field this module added is not in the standard view, so position="move"
        would have nothing to lift; its insertion point is simply updated instead. """
        self.env['om.pen.view'].add_field_rule(
            'res.partner', self.view.id, 'form', 'email', 'function', 'after')
        self._publish()
        self.env['om.pen.view'].move_field_rule(
            'res.partner', self.view.id, 'form', 'email', 'comment', 'after')
        self._publish()

        rule = self.env['om.pen.rule'].search([('field_name', '=', 'email')])
        self.assertEqual(rule.kind, 'add', "it must stay an add rule")
        self.assertEqual(rule.anchor_field, 'comment')
        self.assertEqual(self._order(), ['function', 'website', 'comment', 'email'])


@tagged('post_install', '-at_install')
class TestPagesAndSubviews(PublishMixin, TransactionCase):
    """ Dropping into an existing notebook page, and customizing the list or form
    embedded in an x2many. """

    def setUp(self):
        super().setUp()
        self.view = self.env['ir.ui.view'].create({
            'name': "partner subview form",
            'model': 'res.partner',
            'arch': '''
                <form>
                    <field name="function"/>
                    <notebook>
                        <page name="contacts" string="Contacts">
                            <field name="child_ids">
                                <list>
                                    <field name="name"/>
                                </list>
                                <form>
                                    <field name="name"/>
                                </form>
                            </field>
                        </page>
                        <page string="Unnamed"/>
                    </notebook>
                </form>
            ''',
        })

    def _arch(self):
        return etree.fromstring(
            self.env['res.partner'].get_view(self.view.id, 'form')['arch'])

    def test_a_field_can_be_dropped_into_an_existing_page(self):
        self.env['om.pen.view'].add_field_rule(
            'res.partner', self.view.id, 'form', 'website', False, 'after',
            None, 'contacts')
        self._publish()

        placed = self._arch().xpath("//page[@name='contacts']/field[@name='website']")
        self.assertTrue(placed, "the field must land inside the page that was named")

    def test_dropping_into_a_page_that_is_gone_is_refused(self):
        """ Better than writing an arch whose xpath silently fails to locate. """
        customization = self.env['om.pen.view'].with_context(
            om_pen_skip_apply=True).create({
                'model': 'res.partner', 'view_id': self.view.id, 'view_type': 'form'})
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'website',
            'kind': 'add', 'anchor_page_name': 'nope'})
        with self.assertRaises(ValidationError, msg="an unknown page must be refused"):
            customization._render_arch(draft=True)

    def test_a_field_can_be_added_to_an_embedded_list(self):
        self.env['om.pen.view'].add_subview_field_rule(
            'res.partner', self.view.id, 'form', 'child_ids', 'list', 'email')
        self._publish()

        added = self._arch().xpath("//field[@name='child_ids']/list/field[@name='email']")
        self.assertTrue(added, "the field must land inside the embedded list")
        self.assertFalse(self._arch().xpath("//form/field[@name='email']"),
                         "and not on the view that holds it")

    def test_a_field_can_be_added_to_an_embedded_form(self):
        self.env['om.pen.view'].add_subview_field_rule(
            'res.partner', self.view.id, 'form', 'child_ids', 'form', 'phone')
        self._publish()

        added = self._arch().xpath("//field[@name='child_ids']/form/field[@name='phone']")
        self.assertTrue(added, "the embedded form is addressed separately from the list")

    def test_the_same_field_can_be_customized_in_the_view_and_in_a_subview(self):
        """ The uniqueness of a rule is per embedded view, not per field name. """
        self.env['om.pen.view'].add_subview_field_rule(
            'res.partner', self.view.id, 'form', 'child_ids', 'list', 'email')
        self._publish()
        self.env['om.pen.view'].save_field_rule(
            'res.partner', self.view.id, 'form', 'child_ids/list/email', {'label': "Mail"})
        self._publish()
        self.env['om.pen.view'].add_field_rule(
            'res.partner', self.view.id, 'form', 'email', 'function', 'after')
        self._publish()

        arch = self._arch()
        self.assertEqual(
            arch.xpath("//field[@name='child_ids']/list/field[@name='email']")[0].get('string'),
            "Mail", "the embedded one is renamed")
        self.assertTrue(arch.xpath("//form/field[@name='email']"),
                        "and the one on the view itself is untouched")

    def test_an_x2many_with_no_embedded_view_is_refused(self):
        """ Such a field renders a standalone view, which has to be customized itself. """
        customization = self.env['om.pen.view'].with_context(
            om_pen_skip_apply=True).create({
                'model': 'res.partner', 'view_id': self.view.id, 'view_type': 'form'})
        self.env['om.pen.rule'].create({
            'customize_id': customization.id, 'field_name': 'email', 'kind': 'add',
            'sub_field': 'bank_ids', 'sub_view_type': 'list'})
        with self.assertRaises(ValidationError, msg="there is no inline list to add to"):
            customization._render_arch(draft=True)

    def test_the_embedded_views_of_a_view_can_be_listed(self):
        targets = self.env['om.pen.view'].subview_targets(
            'res.partner', self.view.id, 'form')
        self.assertEqual(len(targets), 1, "only x2many fields with an inline view count")
        self.assertEqual(targets[0]['name'], 'child_ids')
        self.assertEqual(targets[0]['comodel'], 'res.partner')
        self.assertEqual(targets[0]['views'], ['form', 'list'])

    def test_a_field_can_be_moved_into_a_page(self):
        self.env['om.pen.view'].move_field_rule(
            'res.partner', self.view.id, 'form', 'function', False, 'after', 'contacts')
        self._publish()

        arch = self._arch()
        self.assertTrue(arch.xpath("//page[@name='contacts']/field[@name='function']"),
                        "the field must end up inside the page")
        self.assertFalse(arch.xpath("/form/field[@name='function']"),
                         "and must have left the top of the form")


@tagged('post_install', '-at_install')
class TestColumnOptions(PublishMixin, TransactionCase):

    def setUp(self):
        super().setUp()
        self.view = self.env['ir.ui.view'].create({
            'name': "partner options list",
            'model': 'res.partner',
            'arch': '<list><field name="function"/></list>',
        })

    def test_a_column_can_be_made_optional(self):
        """ An optional column is one each user can switch on from the column picker,
        which is a gentler way to declutter a list than hiding the field outright. """
        self.env['om.pen.view'].save_field_rule(
            'res.partner', self.view.id, 'list', 'function', {'optional': 'hide'})
        self._publish()

        arch = etree.fromstring(
            self.env['res.partner'].get_view(self.view.id, 'list')['arch'])
        self.assertEqual(arch.xpath("//field[@name='function']")[0].get('optional'), 'hide')

    def test_a_placeholder_can_be_set(self):
        self.env['om.pen.view'].save_field_rule(
            'res.partner', self.view.id, 'list', 'function', {'placeholder': "e.g. CEO"})
        self._publish()

        arch = etree.fromstring(
            self.env['res.partner'].get_view(self.view.id, 'list')['arch'])
        self.assertEqual(
            arch.xpath("//field[@name='function']")[0].get('placeholder'), "e.g. CEO")


@tagged('post_install', '-at_install')
class TestDraftAndPublish(TransactionCase):
    """ An edit must not reach other users until it is published. """

    def setUp(self):
        super().setUp()
        self.view = self.env['ir.ui.view'].create({
            'name': "partner draft form",
            'model': 'res.partner',
            'arch': '<form><field name="function"/><field name="website"/></form>',
        })
        self.Customize = self.env['om.pen.view']

    def _label(self):
        arch = etree.fromstring(
            self.env['res.partner'].get_view(self.view.id, 'form')['arch'])
        return arch.xpath("//field[@name='function']")[0].get('string')

    def _customization(self):
        return self.Customize.search([('view_id', '=', self.view.id)])

    def test_an_unpublished_change_is_invisible_to_everyone(self):
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})

        self.assertIsNone(self._label(), "nothing may reach the live view before publish")
        self.assertTrue(self._customization().has_draft)
        self.assertEqual(self._customization().draft_count, 1)

    def test_publishing_makes_it_live(self):
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})
        self.Customize.publish('res.partner', self.view.id, 'form')

        self.assertEqual(self._label(), "Role")
        self.assertFalse(self._customization().has_draft, "nothing is pending any more")

    def test_editing_again_leaves_yesterdays_publish_alone(self):
        """ The scenario this feature exists for: publish today, edit tomorrow without
        publishing, and the published version keeps running. """
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})
        self.Customize.publish('res.partner', self.view.id, 'form')

        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Position"})

        self.assertEqual(self._label(), "Role",
                         "the live view must still show what was published")
        self.assertTrue(self._customization().has_draft)

        self.Customize.publish('res.partner', self.view.id, 'form')
        self.assertEqual(self._label(), "Position")

    def test_discarding_goes_back_to_what_is_live(self):
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})
        self.Customize.publish('res.partner', self.view.id, 'form')
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Position"})

        self.Customize.discard_draft('res.partner', self.view.id, 'form')
        rule = self._customization().rule_ids
        self.assertEqual(rule.label, "Role", "the rule goes back to its published state")
        self.assertFalse(self._customization().has_draft)
        self.assertEqual(self._label(), "Role")

    def test_discarding_deletes_a_change_that_was_never_published(self):
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})
        self.Customize.discard_draft('res.partner', self.view.id, 'form')

        self.assertFalse(self._customization().rule_ids, "an unpublished rule is dropped")
        self.assertFalse(self._customization().custom_view_id,
                         "and no view is left behind")

    def test_removing_a_published_change_waits_for_the_next_publish(self):
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})
        self.Customize.publish('res.partner', self.view.id, 'form')

        self.Customize.remove_field_rule('res.partner', self.view.id, 'form', 'function')
        self.assertEqual(self._label(), "Role",
                         "the removal is itself a change, so it is not live yet")
        self.assertTrue(self._customization().rule_ids.to_remove)

        self.Customize.publish('res.partner', self.view.id, 'form')
        self.assertIsNone(self._label())
        self.assertFalse(self._customization().rule_ids, "publish is what deletes it")

    def test_a_draft_that_no_longer_fits_is_flagged_and_cannot_be_published(self):
        """ After a module update the standard view may no longer have what the draft
        points at. The user is told to discard it rather than left with a half state. """
        self.Customize.save_field_rule(
            'res.partner', self.view.id, 'form', 'function', {'label': "Role"})
        self.Customize.publish('res.partner', self.view.id, 'form')

        self.env['om.pen.rule'].create({
            'customize_id': self._customization().id,
            'field_name': 'email', 'kind': 'add', 'anchor_field': 'gone_away',
        })
        self._customization().invalidate_recordset()

        self.assertTrue(self._customization().draft_invalid)
        with self.assertRaises(UserError, msg="publishing a broken draft must be refused"):
            self.Customize.publish('res.partner', self.view.id, 'form')
        self.assertEqual(self._label(), "Role", "and the live view is untouched")

        self.Customize.discard_draft('res.partner', self.view.id, 'form')
        self.assertFalse(self._customization().draft_invalid)
        self.assertEqual(self._label(), "Role")


@tagged('post_install', '-at_install')
class TestFieldNaming(TransactionCase):
    """ The technical name is the user's to choose, but it still has to be a legal
    Postgres identifier and a legal Odoo custom field.

    Each test uses a name of its own: creating a field reloads the registry, and while
    the transaction rolls the column back, the in-memory field list keeps the name, so
    a shared name would clash with whichever test ran first.
    """

    def _create(self, **values):
        return self.env['om.pen.view'].create_field('res.partner', {
            'field_description': "Some Label", 'ttype': 'char', **values})

    def test_a_name_is_derived_from_the_label_when_none_is_given(self):
        self.assertEqual(self._create(field_description="Derived Reference"),
                         'x_derived_reference')

    def test_a_chosen_name_is_used_as_given(self):
        self.assertEqual(self._create(name='x_chosen_ref'), 'x_chosen_ref')

    def test_the_x_prefix_is_added_when_the_user_leaves_it_out(self):
        self.assertEqual(self._create(name='prefixless_ref'), 'x_prefixless_ref',
                         "a custom field must start with x_, enforced by a CHECK"
                         " constraint whose own error is unreadable")

    def test_a_name_is_cleaned_rather_than_rejected(self):
        self.assertEqual(self._create(name='My Cleaned Ref!'), 'x_my_cleaned_ref')

    def test_a_name_that_is_already_taken_is_refused(self):
        self._create(name='x_taken_ref', field_description="One")
        with self.assertRaises(UserError, msg="the clash must be reported, not raised as"
                                              " a database integrity error"):
            self._create(name='x_taken_ref', field_description="Two")

    def test_the_x_prefix_keeps_a_custom_field_clear_of_the_standard_ones(self):
        """ Typing the name of a base field is harmless: it becomes x_<name>. """
        self.assertEqual(self._create(name='partner_phone'), 'x_partner_phone')

    def test_a_name_that_is_too_long_for_postgres_is_refused(self):
        with self.assertRaises(UserError, msg="63 characters is the hard limit"):
            self._create(name='x_' + 'a' * 70)

    def test_a_name_that_is_only_the_prefix_is_refused(self):
        with self.assertRaises(UserError):
            self._create(name='x_')


@tagged('post_install', '-at_install')
class TestRelatedFields(TransactionCase):
    """ A related field mirrors a value from a linked record. It is not stored, so it
    adds no column and deleting it later destroys nothing. """

    def _create(self, related, name):
        return self.env['om.pen.view'].create_field('res.partner', {
            'field_description': "Mirrored", 'name': name, 'related': related})

    def test_the_type_is_taken_from_the_field_at_the_end_of_the_path(self):
        name = self._create('parent_id.website', 'x_parent_site')
        field = self.env['ir.model.fields'].search([
            ('model', '=', 'res.partner'), ('name', '=', name)])
        self.assertEqual(field.ttype, 'char', "the user never picks the type themselves")
        self.assertEqual(field.related, 'parent_id.website')
        self.assertFalse(field.store, "a stored related field would add a real column")
        self.assertTrue(field.readonly, "it mirrors another record, so it is not editable")

    def test_a_relational_target_keeps_its_comodel(self):
        name = self._create('parent_id.country_id', 'x_parent_country')
        field = self.env['ir.model.fields'].search([
            ('model', '=', 'res.partner'), ('name', '=', name)])
        self.assertEqual(field.ttype, 'many2one')
        self.assertEqual(field.relation, 'res.country',
                         "without the comodel the field cannot be instantiated")

    def test_the_value_is_actually_readable(self):
        name = self._create('parent_id.website', 'x_readable_site')
        parent = self.env['res.partner'].create({'name': "Parent", 'website': "example.com"})
        child = self.env['res.partner'].create({'name': "Child", 'parent_id': parent.id})
        self.assertEqual(child[name], parent.website,
                         "the whole point is that the value comes through; res.partner"
                         " normalises the url, so compare against what it stored")

    def test_a_path_that_does_not_go_through_a_link_is_refused(self):
        with self.assertRaises(UserError, msg="every hop but the last must be relational"):
            self._create('website.name', 'x_bad_hop')

    def test_a_path_ending_nowhere_is_refused(self):
        with self.assertRaises(UserError):
            self._create('parent_id.not_a_field', 'x_bad_end')

    def test_a_single_step_path_is_refused(self):
        with self.assertRaises(UserError, msg="that would just be the field itself"):
            self._create('website', 'x_no_hop')

    def test_the_relational_fields_of_a_model_can_be_listed(self):
        steps = self.env['om.pen.view'].related_steps('res.partner')
        by_name = {step['name']: step for step in steps}
        self.assertIn('parent_id', by_name)
        self.assertEqual(by_name['parent_id']['comodel'], 'res.partner')
        self.assertNotIn('website', by_name, "only links are hops")
