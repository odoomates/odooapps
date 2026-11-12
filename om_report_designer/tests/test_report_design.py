from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.om_report_designer.tools import check_layout


def _layout(record_elements=None, columns=None, **table):
    bands = [
        {'id': 'ph', 'kind': 'page_header', 'height': 15, 'elements': [
            {'id': 'title', 'type': 'text', 'text': 'Contacts', 'x': 100, 'y': 2, 'w': 90, 'h': 8},
        ]},
        {'id': 'rec', 'kind': 'record', 'height': 20, 'elements': record_elements or [
            {'id': 'l1', 'type': 'text', 'text': 'Name:', 'x': 0, 'y': 0, 'w': 30, 'h': 6},
            {'id': 'f1', 'type': 'field', 'field': 'name', 'x': 31, 'y': 0, 'w': 60, 'h': 6},
            {'id': 'f2', 'type': 'field', 'field': 'country_id.code', 'x': 31, 'y': 7, 'w': 60, 'h': 6},
        ]},
        {'id': 'pf', 'kind': 'page_footer', 'height': 8, 'elements': [
            {'id': 'pg', 'type': 'page', 'text': 'Page {page} of {pages}', 'x': 150, 'y': 0, 'w': 40, 'h': 6},
        ]},
    ]
    if columns is not None:
        bands.insert(2, {'id': 'lines', 'kind': 'table', 'relation': 'child_ids', 'columns': columns, **table})
    return {'bands': bands}


@tagged('post_install', '-at_install')
class TestReportDesign(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.designer = new_test_user(cls.env, 'om_rd_designer',
                                     groups='base.group_user,om_report_designer.group_om_report_designer_manager')
        cls.user = new_test_user(cls.env, 'om_rd_user', groups='base.group_user,base.group_partner_manager')
        cls.company_partner = cls.env['res.partner'].create({
            'name': 'Bolt <Industries>',
            'is_company': True,
            'country_id': cls.env.ref('base.be').id,
            'child_ids': [
                Command.create({'name': 'Zoe', 'email': 'zoe@example.com', 'color': 2}),
                Command.create({'name': 'Adam', 'email': 'adam@example.com', 'color': 5}),
            ],
        })
        cls.design = cls.env['om.report.design'].create({
            'name': 'Contacts',
            'model_id': cls.env['ir.model']._get('res.partner').id,
            'layout': _layout(columns=[
                {'id': 'c1', 'field': 'name', 'label': 'Contact', 'width': 60},
                {'id': 'c2', 'field': 'email', 'label': 'Email', 'width': 70},
                {'id': 'c3', 'field': 'color', 'label': 'Color', 'width': 20, 'align': 'right', 'sum': True},
            ], order='name'),
        })

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------

    def test_default_layout(self):
        design = self.env['om.report.design'].create({
            'name': 'New', 'model_id': self.env['ir.model']._get('res.partner').id})
        kinds = [band['kind'] for band in design.layout['bands']]
        self.assertEqual(kinds, ['page_header', 'record', 'page_footer'])
        check_layout(self.env, 'res.partner', design.layout)

    def test_check_layout_unknown_field(self):
        with self.assertRaisesRegex(ValidationError, 'does not exist'):
            check_layout(self.env, 'res.partner', _layout([
                {'type': 'field', 'field': 'country_id.no_such_field', 'x': 0, 'y': 0, 'w': 10, 'h': 5}]))
        with self.assertRaisesRegex(ValidationError, 'one2many or many2many'):
            check_layout(self.env, 'res.partner', {'bands': [{'kind': 'table', 'relation': 'country_id'}]})
        with self.assertRaisesRegex(ValidationError, 'line filter'):
            check_layout(self.env, 'res.partner', {'bands': [
                {'kind': 'table', 'relation': 'child_ids', 'domain': "[('no_such_field', '=', 1)]"}]})

    def test_check_layout_cleans_values(self):
        layout = check_layout(self.env, 'res.partner', _layout([{
            'type': 'text', 'text': 'x', 'x': -5, 'y': '3', 'w': 'wide', 'h': 6, 'onclick': 'alert(1)',
            'style': {'color': 'red;background:url(http://evil)', 'background': '#abc', 'align': 'justify',
                      'font_size': 9999},
        }]))
        element = layout['bands'][1]['elements'][0]
        self.assertNotIn('onclick', element)
        self.assertEqual((element['x'], element['y'], element['w']), (0.0, 3.0, 30))
        self.assertEqual(element['style']['color'], '')
        self.assertEqual(element['style']['background'], '#abc')
        self.assertEqual(element['style']['align'], 'left')
        self.assertEqual(element['style']['font_size'], 120)
        self.assertTrue(element['id'])

    def test_check_layout_sorts_bands_and_keeps_one_header(self):
        layout = check_layout(self.env, 'res.partner', {'bands': [
            {'kind': 'page_footer', 'height': 5},
            {'kind': 'record', 'height': 5},
            {'kind': 'page_header', 'height': 5},
            {'kind': 'page_header', 'height': 9},
        ]})
        self.assertEqual([band['kind'] for band in layout['bands']], ['page_header', 'record', 'page_footer'])
        self.assertEqual(layout['bands'][0]['height'], 5)

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------

    def test_render_html(self):
        html = str(self.design._render_html(self.company_partner, 'html'))
        self.assertIn('Bolt &lt;Industries&gt;', html, 'values are escaped')
        self.assertNotIn('Bolt <Industries>', html)
        self.assertIn('>BE<', html)
        self.assertIn('Page 1 of 1', html)
        # lines sorted by name, with their total
        self.assertLess(html.index('Adam'), html.index('Zoe'))
        self.assertIn('adam@example.com', html)
        self.assertIn('o_om_rd_total', html)
        self.assertIn('>7<', html)
        # positions in mm
        self.assertIn('left:31mm;top:7mm;width:60mm;height:6mm', html)
        self.assertIn('<col style="width:60mm"/>', html)

    def test_render_line_filter(self):
        layout = self.design.layout
        layout['bands'][2]['domain'] = "[('email', 'ilike', 'zoe')]"
        self.design.layout = check_layout(self.env, 'res.partner', layout)
        html = str(self.design._render_html(self.company_partner, 'html'))
        self.assertIn('Zoe', html)
        self.assertNotIn('Adam', html)

    def test_render_pdf_parts(self):
        other = self.env['res.partner'].create({'name': 'Other Ltd'})
        records = self.company_partner + other
        html = str(self.design._render_html(records, 'pdf'))
        self.assertEqual(html.count('class="article"'), 2, 'one article per record')
        self.assertEqual(html.count('class="header"'), 2)
        self.assertIn(f'data-oe-id="{other.id}"', html)
        self.assertIn('<span class="page"></span>', html, 'page numbers filled by the PDF engine')

        self.design.page_break = False
        html = str(self.design._render_html(records, 'pdf'))
        self.assertEqual(html.count('class="article"'), 1, 'one flowing article')
        self.assertNotIn('data-oe-id', html)

    def test_render_formats(self):
        renderer_design = self.design
        partner = self.company_partner
        date_layout = _layout([
            {'id': 'd', 'type': 'field', 'field': 'create_date', 'format': 'date', 'x': 0, 'y': 0, 'w': 30, 'h': 6},
            {'id': 'b', 'type': 'field', 'field': 'active', 'x': 0, 'y': 7, 'w': 30, 'h': 6},
            {'id': 'c', 'type': 'field', 'field': 'child_ids', 'x': 0, 'y': 14, 'w': 60, 'h': 6},
        ])
        html = str(renderer_design._render_html(partner, 'html', layout=check_layout(self.env, 'res.partner', date_layout)))
        self.assertIn('✓', html)
        self.assertIn('Adam', html)
        self.assertIn('Zoe', html)

    def test_report_rendering_context(self):
        self.design.action_publish()
        report_name = self.design.report_action_id.report_name
        html = self.env['ir.actions.report']._render_qweb_html(report_name, self.company_partner.ids)[0]
        self.assertIn(b'Bolt &lt;Industries&gt;', html)

    # ------------------------------------------------------------------
    # publishing
    # ------------------------------------------------------------------

    def test_publish(self):
        menu = self.env.ref('base.menu_administration')
        group = self.env.ref('base.group_partner_manager')
        self.design.write({'menu_parent_id': menu.id, 'group_ids': [Command.set(group.ids)]})
        self.design.with_user(self.designer).action_publish()
        design = self.design
        self.assertEqual(design.state, 'published')
        report = design.report_action_id
        self.assertEqual(report.model, 'res.partner')
        self.assertEqual(report.binding_model_id.model, 'res.partner')
        self.assertEqual(report.group_ids, group)
        self.assertEqual(design.view_id.key, report.report_name)
        paper = design.paperformat_id
        self.assertEqual((paper.margin_top, paper.header_spacing, paper.margin_bottom), (25, 15, 18))
        self.assertEqual(paper.dpi, 96)
        self.assertTrue(paper.disable_shrinking)
        self.assertEqual(design.menu_id.parent_id, menu)
        self.assertEqual(design.client_action_id.tag, 'om_report_designer_viewer')

        # changes follow
        design.write({'print_menu': False, 'margin_top': 20})
        self.assertFalse(report.binding_model_id)
        self.assertEqual(paper.margin_top, 35)
        design.menu_parent_id = False
        self.assertFalse(design.menu_id)

        view = design.view_id
        design.action_unpublish()
        self.assertEqual(design.state, 'draft')
        self.assertFalse(report.exists() or view.exists() or paper.exists())

    def test_unlink_removes_report(self):
        self.design.action_publish()
        report = self.design.report_action_id
        self.design.unlink()
        self.assertFalse(report.exists())

    def test_archive_unpublishes(self):
        self.design.action_publish()
        report = self.design.report_action_id
        self.design.active = False
        self.assertFalse(report.exists())
        self.assertEqual(self.design.state, 'draft')

    # ------------------------------------------------------------------
    # designer and access
    # ------------------------------------------------------------------

    def test_designer_save_and_preview(self):
        design = self.design.with_user(self.designer)
        data = design.designer_load()
        self.assertEqual(data['settings']['page_width'], 210)
        self.assertIn({'id': self.company_partner.id, 'name': self.company_partner.display_name}, data['records'])

        layout = data['layout']
        layout['bands'][1]['elements'][0]['text'] = 'Company:'
        preview = design.designer_preview(layout, self.company_partner.id, {'orientation': 'landscape'})
        self.assertIn('Company:', preview)
        self.assertIn('width:277mm', preview, 'the preview uses the unsaved settings')
        self.assertEqual(self.design.layout['bands'][1]['elements'][0]['text'], 'Name:', 'preview writes nothing')

        result = design.designer_save(layout, {'name': 'People', 'orientation': 'landscape'})
        self.assertEqual(self.design.name, 'People')
        self.assertEqual(result['settings']['page_width'], 297)
        self.assertEqual(self.design.layout['bands'][1]['elements'][0]['text'], 'Company:')

        fields = {f['name']: f for f in design.designer_fields('res.partner')}
        self.assertTrue(fields['child_ids']['x2many'])
        self.assertEqual(fields['country_id']['relation'], 'res.country')
        self.assertNotIn('message_ids', fields)

    def test_designer_needs_group(self):
        design = self.design.with_user(self.user)
        with self.assertRaises(AccessError):
            design.designer_load()
        with self.assertRaises(AccessError):
            design.designer_save(self.design.layout)
        with self.assertRaises(AccessError):
            design.action_publish()

    def test_viewer(self):
        self.design.write({'domain': f"[('id', '=', {self.company_partner.id})]"})
        self.design.action_publish()
        data = self.design.with_user(self.user).viewer_load()
        self.assertEqual(data['ids'], self.company_partner.ids)
        self.assertIn('Bolt &lt;Industries&gt;', data['html'])
        self.assertTrue(data['can_print'])
        self.assertFalse(data['can_design'])
        action = self.design.with_user(self.user).viewer_print(data['ids'])
        self.assertEqual(action['type'], 'ir.actions.report')

        self.design.group_ids = self.env.ref('base.group_system')
        with self.assertRaises(AccessError):
            self.design.with_user(self.user).viewer_load()

    def test_layout_checked_on_write(self):
        with self.assertRaisesRegex(ValidationError, 'does not exist'):
            self.env['om.report.design'].create({
                'name': 'Broken',
                'model_id': self.env['ir.model']._get('res.partner').id,
                'layout': _layout([{'type': 'field', 'field': 'nope', 'x': 0, 'y': 0, 'w': 10, 'h': 5}]),
            })
        self.design.layout = _layout()
        self.assertEqual(self.design.layout['bands'][1]['elements'][0]['style']['align'], 'left',
                         'a written layout is completed')
