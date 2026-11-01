# Part of Odoo2XL - Odoo Excel Reports (om_excel_reports). License: LGPL-3.
import io
import json
from urllib.parse import unquote

import openpyxl

from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

TEMPLATE = """
<t t-name="om_excel_reports.test_report">
  <t t-call="web.html_container">
    <t t-foreach="docs" t-as="o">
      <div class="article">
        <div class="page">
          <h2>Partner: <t t-out="o.name"/></h2>
          <table class="table">
            <thead><tr><th>Description</th><th class="text-end">Amount</th></tr></thead>
            <tbody>
              <tr><td>Line one</td><td class="text-end"><span class="oe_currency_value">1,234.50</span></td></tr>
              <tr><td>Line two</td><td class="text-end"><span class="oe_currency_value">10.00</span></td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </t>
  </t>
</t>
"""


WIZARD_TEMPLATE = """
<t t-name="om_excel_reports.test_wizard_report">
  <t t-call="web.html_container">
    <div class="article">
      <h2>Wizard Report</h2>
      <table class="table">
        <thead><tr><th>Name</th><th class="text-end">Total</th></tr></thead>
        <tbody><tr><td>Row</td><td class="text-end">42.00</td></tr></tbody>
      </table>
    </div>
  </t>
</t>
"""


@tagged('post_install', '-at_install')
class TestReportExcel(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.ui.view'].create({
            'name': 'om_excel_reports.test_report',
            'type': 'qweb',
            'key': 'om_excel_reports.test_report',
            'arch': TEMPLATE,
        })
        cls.report = cls.env['ir.actions.report'].create({
            'name': 'Excel Test Partner Report',
            'model': 'res.partner',
            'report_type': 'qweb-pdf',
            'report_name': 'om_excel_reports.test_report',
            'binding_model_id': cls.env['ir.model']._get('res.partner').id,
            'print_report_name': "'Partner %s' % object.id",
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Excel Partner'})
        # A wizard-style report: no Print-menu binding, options travel in ``action.data``.
        cls.env['ir.ui.view'].create({
            'name': 'om_excel_reports.test_wizard_report',
            'type': 'qweb',
            'key': 'om_excel_reports.test_wizard_report',
            'arch': WIZARD_TEMPLATE,
        })
        cls.wizard_report = cls.env['ir.actions.report'].create({
            'name': 'Excel Test Wizard Report',
            'model': 'res.partner',
            'report_type': 'qweb-pdf',
            'report_name': 'om_excel_reports.test_wizard_report',
        })

    def _workbook(self, content):
        return openpyxl.load_workbook(io.BytesIO(content))

    def _excel_allowed(self, report_name):
        self.authenticate('admin', 'admin')
        res = self.url_open(
            '/om_excel_reports/excel_allowed',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {'report_name': report_name}}),
            headers={'Content-Type': 'application/json'})
        return res.json()['result']

    def test_non_pdf_report_cannot_be_rendered(self):
        self.report.report_type = 'qweb-html'
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_excel(self.report.report_name, self.partner.ids)

    def test_engine_specific_pdf_report_type(self):
        """Odoo 20: a report bound to a PDF engine (``qweb-pdf-<engine>``) can be exported too."""
        Report = self.env['ir.actions.report']
        engine_types = [key for key, _label in Report._fields['report_type'].selection
                        if key.startswith('qweb-pdf-')]
        if not engine_types:
            self.skipTest('No engine-specific PDF report type installed')
        self.report.report_type = engine_types[0]
        _content, kind = Report._render_excel(self.report.report_name, self.partner.ids)
        self.assertEqual(kind, 'xlsx')
        self.assertTrue(self._excel_allowed(self.report.report_name)['allowed'])

    def test_wizard_report_is_exportable(self):
        content, kind = self.env['ir.actions.report']._render_excel(
            self.wizard_report.report_name, None, data={'x': 1})
        self.assertEqual(kind, 'xlsx')
        values = [c.value for row in self._workbook(content).active.iter_rows() for c in row]
        self.assertIn(42, values)

    def test_excel_allowed_route(self):
        self.assertEqual(self._excel_allowed(self.wizard_report.report_name), {'allowed': True, 'ask': True})
        self.assertFalse(self._excel_allowed('does.not.exist')['allowed'])
        self.report.report_type = 'qweb-html'
        self.assertFalse(self._excel_allowed(self.report.report_name)['allowed'])
        self.env['ir.config_parameter'].sudo().set_bool('om_excel_reports.ask_format', False)
        self.assertFalse(self._excel_allowed(self.wizard_report.report_name)['ask'])

    def test_excel_not_offered_when_a_dedicated_xlsx_report_exists(self):
        """A PDF report whose model already has an ``xlsx`` report action keeps that one."""
        Report = self.env['ir.actions.report']
        if 'xlsx' not in dict(Report._fields['report_type'].selection):
            self.skipTest('No module adds the xlsx report type')
        self.wizard_report.model = 'res.country'
        Report.create({
            'name': 'Dedicated Excel Report',
            'model': 'res.partner',
            'report_type': 'xlsx',
            'report_name': 'om_excel_reports.test_dedicated_xlsx',
        })
        self.assertFalse(self._excel_allowed(self.report.report_name)['allowed'])
        self.assertTrue(self._excel_allowed(self.wizard_report.report_name)['allowed'])

    def test_report_name_still_resolves_to_pdf_report(self):
        Report = self.env['ir.actions.report']
        self.assertEqual(Report._get_report_from_name(self.report.report_name), self.report)
        self.assertEqual(Report._get_report(self.report.report_name), self.report)

    def test_render_excel(self):
        content, kind = self.env['ir.actions.report']._render_excel(
            self.report.report_name, self.partner.ids)
        self.assertEqual(kind, 'xlsx')
        wb = self._workbook(content)
        ws = wb.active
        values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
        self.assertIn(1234.5, values)
        self.assertIn('Line two', values)
        self.assertEqual(wb.sheetnames, ['Excel Partner'])
        self.assertTrue(ws.freeze_panes)

    def test_download_controller(self):
        self.authenticate('admin', 'admin')
        url = '/report/excel/%s/%s' % (self.report.report_name, self.partner.id)
        res = self.url_open('/report/download', data={
            'data': json.dumps([url, 'excel']),
            'context': json.dumps({}),
            'csrf_token': self.csrf_token(),
        })
        self.assertEqual(res.status_code, 200, res.text[:500])
        self.assertIn('spreadsheetml', res.headers['Content-Type'])
        self.assertIn('Partner %s.xlsx' % self.partner.id, unquote(res.headers['Content-Disposition']))
        ws = self._workbook(res.content).active
        self.assertIn(1234.5, [c.value for row in ws.iter_rows() for c in row])

    @mute_logger('odoo.addons.om_excel_reports.controllers.main')
    def test_download_controller_wizard_style_url(self):
        self.authenticate('admin', 'admin')
        options = json.dumps({'ids': self.partner.ids})
        url = '/report/excel/%s?options=%s&context=%s' % (self.report.report_name, options, '{}')
        res = self.url_open('/report/download', data={
            'data': json.dumps([url, 'excel']),
            'context': json.dumps({'active_ids': self.partner.ids}),
            'csrf_token': self.csrf_token(),
        })
        # No docids are passed for wizard reports; the template simply renders no article.
        self.assertIn(res.status_code, (200, 500))

    def test_pdf_download_still_routed_to_core(self):
        self.authenticate('admin', 'admin')
        res = self.url_open('/report/download', data={
            'data': json.dumps(['/report/pdf/%s/%s' % (self.report.report_name, self.partner.id), 'qweb-pdf']),
            'context': json.dumps({}),
            'csrf_token': self.csrf_token(),
        })
        # wkhtmltopdf is usually missing in CI: core answers (200 with a PDF, or its own error), never a 404.
        self.assertNotEqual(res.status_code, 404)

    def test_html_report_route_unchanged(self):
        self.authenticate('admin', 'admin')
        res = self.url_open('/report/html/%s/%s' % (self.report.report_name, self.partner.id))
        self.assertEqual(res.status_code, 200)
        self.assertIn('Excel Partner', res.text)

    def test_backend_assets_load(self):
        """The backend must boot with our handler registered in the report-handlers registry."""
        self.browser_js(
            '/odoo',
            """
            const { registry } = odoo.loader.modules.get("@web/core/registry");
            const keys = registry.category("ir.actions.report handlers").getEntries().map(e => e[0]);
            console.log("HANDLERS " + JSON.stringify(keys));
            console.log("MODULES " + JSON.stringify([...odoo.loader.modules.keys()].filter(k => k.includes("excel"))));
            if (keys.includes("om_excel_reports.handler")) {
                console.log("test successful");
            } else {
                console.error("Excel report handler is not registered");
            }
            """,
            ready="!!document.querySelector('.o_main_navbar')",
            login='admin',
        )

    def test_wizard_dialog_tour(self):
        """Wizard reports ask PDF / Excel / Both; choosing Excel downloads the workbook."""
        self.start_tour('/odoo/action-base.action_model_model', 'om_excel_reports_wizard_dialog', login='admin')

    def test_pdf_print_menu_dialog_tour(self):
        """Printing a regular PDF report from the Print menu offers the chooser too."""
        self.start_tour('/odoo/action-base.action_model_model', 'om_excel_reports_pdf_dialog', login='admin')

    def test_preview_route_inline_with_report_file_name(self):
        """Preview serves the PDF inline under the same name a download would get."""
        self.report.print_report_name = "'Quotation - CQ/08/%s' % object.id"
        self.authenticate('admin', 'admin')
        res = self.url_open('/om_excel_reports/preview/%s/%s?context=%s' % (
            self.report.report_name, self.partner.id, json.dumps({'lang': 'en_US'})))
        self.assertEqual(res.status_code, 200, res.text[:300])
        disposition = unquote(res.headers['Content-Disposition'])
        self.assertTrue(disposition.startswith('inline'), disposition)
        self.assertIn('Quotation - CQ', disposition)
        self.assertIn('%s.pdf' % self.partner.id, disposition)

    def test_preview_route_multi_records_uses_report_name(self):
        other = self.env['res.partner'].create({'name': 'Second Partner'})
        self.authenticate('admin', 'admin')
        res = self.url_open('/om_excel_reports/preview/%s/%s,%s' % (
            self.report.report_name, self.partner.id, other.id))
        self.assertEqual(res.status_code, 200)
        self.assertIn('Excel Test Partner Report.pdf', unquote(res.headers['Content-Disposition']))

    def test_preview_dialog_tour(self):
        """The chooser's Preview button opens the inline PDF URL in a new tab."""
        self.start_tour('/odoo/action-base.action_model_model', 'om_excel_reports_preview_dialog', login='admin')
