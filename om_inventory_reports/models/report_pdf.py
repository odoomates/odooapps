from datetime import date, datetime

from odoo import api, fields, models
from odoo.tools.misc import format_amount, format_date, format_datetime, formatLang

from ..lib.xlsx import build_csv, build_xlsx

NUMERIC = ('float', 'monetary', 'int', 'percent', 'days', 'ratio')
MIMETYPES = {
    'pdf': 'application/pdf',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv': 'text/csv;charset=utf-8',
}


class OmInventoryReportExport(models.AbstractModel):
    """Formatting shared by the PDF, Excel and CSV exports."""
    _name = 'om.inventory.report.export'
    _description = 'Inventory Report Export'

    @api.model
    def _om_export(self, params):
        report = self.env['om.inventory.report']._om_report(params['report'])
        return report.om_export_data(params.get('options'), params.get('expanded'), params.get('expand_all'))

    @api.model
    def _om_render_file(self, params):
        """(content, file name, mimetype) of a report exported as params['format']."""
        file_format = params.get('format')
        if file_format not in MIMETYPES:
            raise ValueError("Unknown format: %s" % file_format)
        if file_format == 'pdf':
            report = self.env['om.inventory.report']._om_report(params['report'])
            options = report._om_normalize_options(params.get('options'))
            export = {'title': report._om_report_title(), 'subtitle': report._om_subtitle(options)}
            content = self.env['ir.actions.report']._render_qweb_pdf(
                'om_inventory_reports.action_report_inventory', data={'params': params})[0]
        else:
            export = self._om_export(params)
            content = (build_xlsx if file_format == 'xlsx' else build_csv)(self, export)
        return content, self._om_filename(export, file_format), MIMETYPES[file_format]

    @api.model
    def _om_cell(self, export, line, column):
        """The value of a cell as printed, '' when empty."""
        if column.get('detail_only') and line.get('kind') != 'detail':
            return ''
        value = (line.get('values') or {}).get(column['key'])
        if value is None or value is False or value == '':
            return ''
        kind = column['type']
        if kind in NUMERIC and line.get('kind') == 'detail' and not value and column['key'] != 'balance':
            return ''
        if kind == 'float':
            return formatLang(self.env, value, digits=export['digits'])
        if kind == 'monetary':
            return format_amount(self.env, value, export['currency'])
        if kind == 'int':
            return formatLang(self.env, value, digits=0)
        if kind == 'percent':
            return '%s %%' % formatLang(self.env, value, digits=1)
        if kind == 'ratio':
            return formatLang(self.env, value, digits=2)
        if kind == 'days':
            return self.env._("%s d", formatLang(self.env, round(value), digits=0))
        if kind == 'datetime':
            return format_datetime(self.env, fields.Datetime.to_datetime(value), dt_format='short')
        if kind == 'date':
            return format_date(self.env, value)
        return str(value)

    @api.model
    def _om_local_datetime(self, value):
        """A UTC datetime of the report in the user's time zone, without tzinfo (for Excel)."""
        value = fields.Datetime.to_datetime(value)
        return fields.Datetime.context_timestamp(self, value).replace(tzinfo=None)

    @api.model
    def _om_filename(self, export, extension):
        name = export['title']
        if export['subtitle']:
            name = '%s - %s' % (name, export['subtitle'])
        name = ''.join(c if c.isalnum() or c in ' -_.()' else '-' for c in name)
        return '%s.%s' % (name, extension)


class ReportOmInventoryReports(models.AbstractModel):
    _name = 'report.om_inventory_reports.report_inventory'
    _description = 'Inventory Report PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        exporter = self.env['om.inventory.report.export']
        export = exporter._om_export(data['params'])
        return {
            'doc_ids': docids,
            'export': export,
            'company': export['company'],
            'cell': lambda line, column: exporter._om_cell(export, line, column),
            'format_kpi': lambda kpi: exporter._om_cell(export, {'kind': 'total', 'values': {'v': kpi['value']}},
                                                       {'key': 'v', 'type': kpi['type']}) or '0',
            'numeric': NUMERIC,
            'row_class': self._om_row_class,
            'cell_class': self._om_cell_class,
            'printed_on': format_datetime(self.env, datetime.now(), dt_format='short'),
            'today': date.today(),
        }

    @api.model
    def _om_row_class(self, line):
        kind = line['kind']
        if kind in ('group', 'leaf') and line.get('has_children'):
            kind = 'group'
        return 'o_om_%s o_om_group_%s' % (kind, line['level']) if kind == 'group' else 'o_om_%s' % kind

    @api.model
    def _om_cell_class(self, line, column):
        classes = []
        if column['type'] in NUMERIC:
            classes.append('o_om_num')
            value = (line.get('values') or {}).get(column['key'])
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
                classes.append('o_om_negative')
        return ' '.join(classes)
