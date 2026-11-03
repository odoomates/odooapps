# Part of Odoo2XL - Odoo Excel Reports (om_excel_reports). License: LGPL-3.
import json
import logging
from urllib.parse import parse_qsl, urlsplit

import werkzeug.exceptions

from odoo.http import content_disposition, request, route, serialize_exception
from odoo.tools.misc import html_escape
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.web.controllers.report import ReportController

from ..models.ir_actions_report import XLSX_MIMETYPE, is_pdf_report_type

_logger = logging.getLogger(__name__)


class ReportExcelController(ReportController):

    @staticmethod
    def _report_filename(report, docids, extension):
        """File name used by Odoo for a printed report, with ``extension``.

        Mirrors core: the report's "Printed Report Name" expression for a single record
        (e.g. ``Quotation - CQ/08/0009``), otherwise the report name.
        """
        filename = '%s.%s' % (report.name, extension)
        if docids:
            if isinstance(docids, str):
                docids = [int(x) for x in docids.split(',') if x.isdigit()]
            records = request.env[report.model].browse(docids)
            if report.print_report_name and len(records) == 1:
                name = safe_eval(report.print_report_name, {'object': records, 'time': time})
                filename = '%s.%s' % (name, extension)
        return filename

    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        """Add the ``excel`` converter: /report/excel/<reportname>[/<docids>]."""
        if converter != 'excel':
            return super().report_routes(reportname, docids=docids, converter=converter, **data)
        context = dict(request.env.context)
        if docids:
            docids = [int(i) for i in docids.split(',') if i.isdigit()]
        if data.get('options'):
            data.update(json.loads(data.pop('options')))
        if data.get('context'):
            data['context'] = json.loads(data['context'])
            context.update(data['context'])
        content = request.env['ir.actions.report'].with_context(context)._render_excel(
            reportname, docids, data=data)[0]
        return request.make_response(content, headers=[
            ('Content-Type', XLSX_MIMETYPE), ('Content-Length', len(content))])

    @route()
    def report_download(self, data, context=None, token=None, readonly=True):
        """Handle the download of ``excel`` reports; everything else goes to core."""
        requestcontent = json.loads(data)
        url, type_ = requestcontent[0], requestcontent[1]
        if type_ != 'excel':
            return super().report_download(data, context=context, token=token, readonly=readonly)
        reportname = '???'
        try:
            reportname = url.split('/report/excel/')[1].split('?')[0]
            docids = None
            if '/' in reportname:
                reportname, docids = reportname.split('/')
            if docids:
                response = self.report_routes(reportname, docids=docids, converter='excel', context=context)
            else:
                query = dict(parse_qsl(urlsplit(url).query))
                if 'context' in query:
                    context = json.dumps({**json.loads(context or '{}'), **json.loads(query.pop('context'))})
                response = self.report_routes(reportname, converter='excel', context=context, **query)

            report = request.env['ir.actions.report']._get_report_from_name(reportname)
            filename = self._report_filename(report, docids, 'xlsx')
            response.headers.add('Content-Disposition', content_disposition(filename))
            return response
        except Exception as exc:
            _logger.warning('Error while generating Excel report %s', reportname, exc_info=True)
            error = {'code': 0, 'message': 'Odoo Server Error', 'data': serialize_exception(exc)}
            res = request.make_response(html_escape(json.dumps(error)))
            raise werkzeug.exceptions.InternalServerError(response=res) from exc

    @route([
        '/om_excel_reports/preview/<reportname>',
        '/om_excel_reports/preview/<reportname>/<docids>',
    ], type='http', auth='user')
    def report_preview(self, reportname, docids=None, **data):
        """Show a PDF report inline (new browser tab) under its real file name.

        The ``inline`` Content-Disposition carries the same name as a normal download, so
        "Download" in the browser's PDF viewer saves e.g. ``Quotation - CQ_08_0009.pdf``
        instead of the record id.
        """
        response = self.report_routes(reportname, docids=docids, converter='pdf', **data)
        report = request.env['ir.actions.report']._get_report_from_name(reportname)
        filename = self._report_filename(report, docids, 'pdf')
        response.headers['Content-Disposition'] = content_disposition(filename, disposition_type='inline')
        return response

    @route('/om_excel_reports/excel_allowed', type='jsonrpc', auth='user', readonly=True)
    def excel_allowed(self, report_name):
        """Tell the web client how to treat a PDF report.

        :return: ``{'allowed': bool, 'ask': bool}`` - whether the report may be exported to
            Excel, and whether the PDF / Excel / Both chooser should be shown before printing
            (system parameter ``om_excel_reports.ask_format``, on by default). A report that
            already has a dedicated Excel export (an ``xlsx`` report action on the same model,
            from another module) is not offered a second one.
        """
        Report = request.env['ir.actions.report']
        report = Report._get_report_from_name(report_name)
        dedicated = report and Report.sudo().search_count(
            [('model', '=', report.model), ('report_type', '=', 'xlsx')], limit=1)
        allowed = bool(report and is_pdf_report_type(report.report_type) and not dedicated)
        ask = request.env['ir.config_parameter'].sudo().get_param(
            'om_excel_reports.ask_format', 'True').strip().lower() not in ('false', '0', '')
        return {'allowed': allowed, 'ask': ask}
