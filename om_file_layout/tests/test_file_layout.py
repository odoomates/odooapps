from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestFileLayout(TransactionCase):
    """ Files of contacts: any model can be exported. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'om_file_user', groups='base.group_user,base.group_partner_manager')
        Partner = cls.env['res.partner']
        cls.partners = Partner.create([
            {'name': 'Alpha Trading', 'ref': 'A1', 'street': '1500'},
            {'name': 'Beta Supplies', 'ref': False, 'street': '250.5'},
        ])
        cls.model_id = cls.env['ir.model']._get_id('res.partner')

    def layout(self, **values):
        return self.env['file.layout'].create({'name': 'Partners', 'model_id': self.model_id, **values})

    def wizard(self, layout, records=None):
        records = records or self.partners
        context = {'active_model': 'res.partner', 'active_ids': records.ids, 'default_layout_id': layout.id}
        return Form(self.env['file.export.wizard'].with_user(self.user).with_context(**context)).save()

    def test_csv(self):
        layout = self.layout(file_format='csv', csv_separator=';', line_ending='lf', column_ids=[
            (0, 0, {'name': 'Name', 'expression': 'record.name', 'upper': True}),
            (0, 0, {'name': 'Limit', 'expression': 'float(record.street)', 'value_type': 'decimal',
                    'decimal_separator': ','}),
        ])
        content = layout._render(self.partners)['content'].decode()
        self.assertEqual(content, 'Name;Limit\nALPHA TRADING;1500,00\nBETA SUPPLIES;250,50\n')

    def test_fixed_width_with_header_and_footer(self):
        layout = self.layout(file_format='fixed', line_ending='lf', column_ids=[
            (0, 0, {'section': 'header', 'name': 'Type', 'expression': "'H'", 'width': 1}),
            (0, 0, {'section': 'header', 'name': 'Date', 'expression': 'today', 'value_type': 'date',
                    'date_format': '%Y', 'width': 4}),
            (0, 0, {'name': 'Type', 'expression': "'D'", 'width': 1}),
            (0, 0, {'name': 'Name', 'expression': 'record.name', 'width': 8}),
            (0, 0, {'name': 'Amount', 'expression': 'float(record.street)', 'value_type': 'decimal',
                    'implied_decimals': True, 'width': 8, 'align': 'right', 'pad_char': '0'}),
            (0, 0, {'section': 'footer', 'name': 'Type', 'expression': "'T'", 'width': 1}),
            (0, 0, {'section': 'footer', 'name': 'Count', 'expression': 'count', 'value_type': 'integer',
                    'width': 3, 'align': 'right', 'pad_char': '0'}),
            (0, 0, {'section': 'footer', 'name': 'Sum', 'expression': 'sum(float(r.street) for r in records)',
                    'value_type': 'decimal', 'implied_decimals': True, 'width': 8, 'align': 'right',
                    'pad_char': '0'}),
        ])
        result = layout._render(self.partners)
        lines = result['content'].decode().splitlines()
        self.assertEqual(len(lines[0]), 5)
        self.assertEqual(lines[1], 'DAlpha Tr00150000')
        self.assertEqual(lines[2], 'DBeta Sup00025050')
        self.assertEqual(lines[3], 'T00200175050')
        self.assertTrue(any('longer than 8' in problem for problem in result['problems']))

    def test_problems_and_export(self):
        layout = self.layout(column_ids=[
            (0, 0, {'name': 'Name', 'expression': 'record.name'}),
            (0, 0, {'name': 'Reference', 'expression': 'record.ref', 'required': True}),
            (0, 0, {'name': 'Broken', 'expression': 'record.no_such_field'}),
        ])
        wizard = self.wizard(layout)
        self.assertTrue(wizard.has_problems)
        self.assertIn('Beta Supplies', wizard.problems)
        self.assertIn('Reference: empty', wizard.problems)
        self.assertIn('Broken', wizard.problems)
        self.assertIn('Alpha Trading', wizard.preview)

        action = wizard.action_download()
        export = self.env['file.export'].search([('layout_id', '=', layout.id)])
        self.assertEqual((export.record_count, export.line_count, export.create_uid),
                         (2, 2, self.user))
        self.assertEqual(sorted(export.res_ids), sorted(self.partners.ids))
        self.assertIn(str(export.attachment_id.id), action['url'])
        export.attachment_id.with_user(self.user).read(['name'])
        self.assertTrue(export.name.startswith('Partners_') and export.name.endswith('.csv'))

    def test_xlsx(self):
        layout = self.layout(file_format='xlsx', column_ids=[
            (0, 0, {'name': 'Name', 'expression': 'record.name'}),
            (0, 0, {'name': 'Limit', 'expression': 'float(record.street)', 'value_type': 'decimal'}),
        ])
        content = layout._render(self.partners)['content']
        self.assertEqual(content[:2], b'PK', 'an Excel workbook')

    def test_action_menu(self):
        layout = self.layout()
        bindings = self.env['ir.actions.actions'].get_bindings('res.partner').get('action', [])
        self.assertIn(layout.ref_ir_act_window.id, [binding['id'] for binding in bindings])
        layout.action_menu = False
        self.assertFalse(layout.ref_ir_act_window)

    def test_encoding(self):
        self.partners[0].name = 'Café Zoë'
        layout = self.layout(encoding='ascii', column_titles=False, column_ids=[
            (0, 0, {'name': 'Name', 'expression': 'record.name'})])
        self.assertEqual(layout._render(self.partners[0])['content'], b'Caf? Zo?\r\n')
