from lxml import etree

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestCustomizerTour(HttpCase):
    """ The overlay, the navbar button and the panel only exist in the browser, so the
    only way to know they work is to drive them. """

    def test_a_field_can_be_renamed_from_customize_mode(self):
        partner_form = self.env.ref('base.view_partner_form')
        action = self.env['ir.actions.act_window'].create({
            'name': "Customizer Tour",
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.env.ref('base.partner_admin').id,
            'view_id': partner_form.id,
        })

        self.start_tour('/odoo/action-%s' % action.id, 'om_pen_tour',
                        login='admin', timeout=90)

        customization = self.env['om.pen.view'].search([('view_id', '=', partner_form.id)])
        self.assertTrue(customization, "the tour must have created a customization")
        self.assertEqual(customization.rule_ids.field_name, 'function')
        self.assertEqual(customization.rule_ids.label, "Role On Site")
        self.assertTrue(customization.custom_view_id.active,
                        "the generated view must be live, not just stored")

    def test_a_field_can_be_added_from_customize_mode(self):
        """ The floating button, the dialog and the click-to-place step. A cut-down view
        is used so the tour controls exactly which fields are on screen. """
        view = self.env['ir.ui.view'].create({
            'name': "partner customizer tour form",
            'model': 'res.partner',
            'arch': '<form><group><field name="function"/></group></form>',
        })
        action = self.env['ir.actions.act_window'].create({
            'name': "Add Field Tour",
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.env.ref('base.partner_admin').id,
            'view_id': view.id,
        })

        self.start_tour('/odoo/action-%s' % action.id, 'om_pen_add_field_tour',
                        login='admin', timeout=90)

        rule = self.env['om.pen.rule'].search([('field_name', '=', 'website')])
        self.assertEqual(rule.kind, 'add', "the tour must have created an add rule")
        self.assertEqual(rule.anchor_field, 'function',
                         "the field it was dropped on becomes the anchor")

    def test_a_field_can_be_dragged_to_a_new_place(self):
        """ Dragging is pointer based, so only a browser can prove it works. """
        view = self.env['ir.ui.view'].create({
            'name': "partner drag tour form",
            'model': 'res.partner',
            'arch': '''
                <form>
                    <group>
                        <field name="function"/>
                        <field name="website"/>
                        <field name="comment"/>
                    </group>
                </form>
            ''',
        })
        action = self.env['ir.actions.act_window'].create({
            'name': "Drag Tour",
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.env.ref('base.partner_admin').id,
            'view_id': view.id,
        })

        self.start_tour('/odoo/action-%s' % action.id, 'om_pen_drag_tour',
                        login='admin', timeout=90)

        rule = self.env['om.pen.rule'].search([
            ('field_name', '=', 'function'), ('kind', '=', 'move')])
        self.assertTrue(rule, "the drag must have created a move rule")
        self.assertEqual(rule.anchor_field, 'comment',
                         "the field it was dropped on becomes the anchor")
        self.assertEqual(rule.position, 'before',
                         "the tour drops on the top half of the target, and which half"
                         " the pointer is on is what decides before or after")

        arch = etree.fromstring(self.env['res.partner'].get_view(view.id, 'form')['arch'])
        order = [node.get('name') for node in arch.xpath('//field')]
        self.assertEqual(order, ['website', 'function', 'comment'],
                         "the dragged field must have left its old place and landed"
                         " immediately before the field it was dropped on")

    def _notebook_view(self):
        return self.env['ir.ui.view'].create({
            'name': "partner notebook tour form",
            'model': 'res.partner',
            'arch': '''
                <form>
                    <group>
                        <field name="function"/>
                    </group>
                    <notebook>
                        <page name="contacts" string="Contacts">
                            <field name="child_ids">
                                <list><field name="name"/></list>
                            </field>
                        </page>
                    </notebook>
                </form>
            ''',
        })

    def _action_for(self, view):
        return self.env['ir.actions.act_window'].create({
            'name': "Customizer Tour",
            'res_model': 'res.partner',
            'view_mode': 'form',
            'res_id': self.env.ref('base.partner_admin').id,
            'view_id': view.id,
        })

    def test_a_field_can_be_dragged_onto_a_notebook_page(self):
        view = self._notebook_view()
        self.start_tour('/odoo/action-%s' % self._action_for(view).id,
                        'om_pen_page_drop_tour', login='admin', timeout=90)

        rule = self.env['om.pen.rule'].search([('field_name', '=', 'function')])
        self.assertEqual(rule.anchor_page_name, 'contacts',
                         "the tab that was dropped on names the page")
        arch = etree.fromstring(self.env['res.partner'].get_view(view.id, 'form')['arch'])
        self.assertTrue(arch.xpath("//page[@name='contacts']/field[@name='function']"),
                        "the field must have moved inside the page")

    def test_a_field_can_be_added_to_an_embedded_list(self):
        view = self._notebook_view()
        self.start_tour('/odoo/action-%s' % self._action_for(view).id,
                        'om_pen_subview_tour', login='admin', timeout=90)

        rule = self.env['om.pen.rule'].search([('field_name', '=', 'email')])
        self.assertEqual(rule.sub_field, 'child_ids')
        self.assertEqual(rule.sub_view_type, 'list',
                         "the embedded list is addressed separately from the form")

    def test_unsaved_changes_are_announced_and_guarded(self):
        view = self.env['ir.ui.view'].create({
            'name': "partner unsaved tour form",
            'model': 'res.partner',
            'arch': '<form><group><field name="function"/></group></form>',
        })
        self.start_tour('/odoo/action-%s' % self._action_for(view).id,
                        'om_pen_unsaved_tour', login='admin', timeout=90)

        rule = self.env['om.pen.rule'].search([('field_name', '=', 'function')])
        self.assertEqual(rule.label, "Role",
                         "Ctrl+Enter must have applied the first edit, and the discarded"
                         " second edit must not have been saved")

    def test_a_new_field_can_be_created_with_a_chosen_name(self):
        view = self.env['ir.ui.view'].create({
            'name': "partner new field tour form",
            'model': 'res.partner',
            'arch': '<form><group><field name="function"/></group></form>',
        })
        self.start_tour('/odoo/action-%s' % self._action_for(view).id,
                        'om_pen_new_field_tour', login='admin', timeout=90)

        field = self.env['ir.model.fields'].search([
            ('model', '=', 'res.partner'), ('name', '=', 'x_our_ref')])
        self.assertTrue(field, "the technical name the user typed must win over the"
                               " one derived from the label")
        self.assertEqual(field.field_description, "Internal Reference")
        self.assertEqual(field.ttype, 'text', "the type picked in the grid must be used")

    def test_a_related_field_can_be_built_by_following_a_link(self):
        # a record whose parent actually has a website: an empty readonly field renders
        # with no height, which the tour would not see, and the value is the point
        parent = self.env['res.partner'].create({
            'name': "Tour Parent", 'website': "https://example.com"})
        child = self.env['res.partner'].create({
            'name': "Tour Child", 'parent_id': parent.id})
        view = self.env['ir.ui.view'].create({
            'name': "partner related tour form",
            'model': 'res.partner',
            'arch': '<form><group><field name="function"/></group></form>',
        })
        action = self.env['ir.actions.act_window'].create({
            'name': "Related Tour", 'res_model': 'res.partner', 'view_mode': 'form',
            'res_id': child.id, 'view_id': view.id,
        })
        self.start_tour('/odoo/action-%s' % action.id,
                        'om_pen_related_tour', login='admin', timeout=90)

        field = self.env['ir.model.fields'].search([
            ('model', '=', 'res.partner'), ('name', '=', 'x_parent_site')])
        self.assertEqual(field.related, 'parent_id.website',
                         "the path built in the dialog is what gets stored")
        self.assertEqual(field.ttype, 'char', "the type comes from the end of the path")
        self.assertFalse(field.store, "a related field adds no column")

    def test_a_condition_can_be_built_without_typing_python(self):
        view = self.env['ir.ui.view'].create({
            'name': "partner condition tour form",
            'model': 'res.partner',
            'arch': '<form><group><field name="function"/><field name="website"/></group></form>',
        })
        self.start_tour('/odoo/action-%s' % self._action_for(view).id,
                        'om_pen_condition_tour', login='admin', timeout=90)

        rule = self.env['om.pen.rule'].search([('field_name', '=', 'function')])
        self.assertEqual(rule.invisible, 'not website',
                         "the rows must compile to the expression the view carries")
        self.assertEqual(rule.condition_data.get('invisible'),
                         {'join': 'and', 'rows': [{'field': 'website',
                                                   'operator': 'not set', 'value': ''}]},
                         "and the rows are kept so the panel can show them again")

        arch = self.env['res.partner'].get_view(view.id, 'form')['arch']
        self.assertIn('invisible="not website"', arch,
                      "the generated expression must reach the view")
