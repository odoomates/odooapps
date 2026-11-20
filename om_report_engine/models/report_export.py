from datetime import datetime

from odoo import api, fields, models
from odoo.tools.misc import format_amount, format_date, format_datetime, formatLang

from ..lib.xlsx import build_csv, build_xlsx
from .report import NUMERIC_TYPES

# the description of the files made only to be downloaded
DOWNLOAD_MARK = 'om_report_engine download'

MIMETYPES = {
    'pdf': 'application/pdf',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv': 'text/csv;charset=utf-8',
}


class OmReportExport(models.AbstractModel):
    """The PDF, Excel and CSV files of the dynamic reports, from the same lines as the screen."""
    _name = 'om.report.export'
    _description = 'Dynamic Report Export'

    @api.model
    def _om_export(self, params):
        report = self.env['om.report']._om_get_report_model(params.get('model'))
        return report.om_export_data(params.get('options'), params.get('expanded'), params.get('expand_all'))

    @api.model
    def _om_render_file(self, params):
        """(content, file name, mimetype) of a report exported as params['format']."""
        file_format = params.get('format')
        if file_format not in MIMETYPES:
            raise ValueError("Unknown format: %s" % file_format)
        if file_format == 'pdf':
            # the report itself builds the lines (_get_report_values): only its title is needed here
            report = self.env['om.report']._om_get_report_model(params.get('model'))
            options = report._om_normalize_options(params.get('options'))
            report = report._om_prepare(options)
            export = {'title': report._om_report_title(), 'subtitle': report._om_subtitle(options)}
            content = self.env['ir.actions.report']._render_qweb_pdf(
                'om_report_engine.action_report_dynamic', data={'params': params})[0]
        else:
            export = self._om_export(params)
            content = (build_xlsx if file_format == 'xlsx' else build_csv)(self, export)
        return content, self._om_filename(export, file_format), MIMETYPES[file_format]

    @api.model
    def _om_attachment(self, model, options, file_format='pdf', expand_all=True, name=None, res_model=False,
                       res_id=False):
        """The report exported as a file, kept as an attachment (to download it or send it)."""
        content, filename, mimetype = self._om_render_file(
            {'model': model, 'format': file_format, 'options': options, 'expand_all': expand_all})
        Attachment = self.env['ir.attachment']
        if not res_model:
            # a file only to download: the user's older ones are removed
            Attachment.search([('res_model', '=', False), ('description', '=', DOWNLOAD_MARK),
                               ('create_uid', '=', self.env.uid),
                               ('create_date', '<', fields.Datetime.subtract(fields.Datetime.now(), hours=1))]
                              ).unlink()
        return Attachment.create({
            'name': name or filename,
            'raw': content,
            'mimetype': mimetype,
            'res_model': res_model,
            'res_id': res_id,
            'description': False if res_model else DOWNLOAD_MARK,
        })

    @api.model
    def _om_download_action(self, attachment):
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % attachment.id,
                'target': 'download'}

    @api.model
    def _om_cell(self, export, line, column):
        """The value of a cell as printed, '' when empty."""
        if column.get('detail_only') and line.get('kind') not in ('detail', 'opening', 'closing'):
            return ''
        value = (line.get('values') or {}).get(column['key'])
        if value is None or value is False or value == '':
            return ''
        kind = (line.get('types') or {}).get(column['key']) or column['type']
        if column.get('blank_zero') and value == 0 and line.get('kind') == 'detail':
            return ''
        if kind == 'monetary':
            rounding = export.get('rounding')
            if rounding:
                return self._om_rounded_amount(value, export['currency'], rounding)
            return format_amount(self.env, value, export['currency'])
        if kind == 'float':
            return formatLang(self.env, value, digits=column.get('digits', 2))
        if kind == 'int':
            return formatLang(self.env, value, digits=0)
        if kind == 'percent':
            return '%s %%' % formatLang(self.env, value, digits=1)
        if kind == 'ratio':
            return formatLang(self.env, value, digits=2)
        if kind == 'days':
            return self.env._("%s days", formatLang(self.env, value, digits=column.get('digits', 1)))
        if kind == 'datetime':
            return format_datetime(self.env, fields.Datetime.to_datetime(value), dt_format='short')
        if kind == 'date':
            return format_date(self.env, value)
        return str(value)

    @api.model
    def _om_kpi_value(self, export, kpi):
        """A key figure as printed."""
        column = {'key': 'value', 'type': kpi.get('type') or 'float', 'digits': export.get('digits', 2)}
        return self._om_cell(export, {'kind': 'total', 'values': {'value': kpi.get('value') or 0.0}}, column) or '0'

    @api.model
    def _om_rounded_amount(self, value, currency, rounding):
        """An amount in units, thousands or millions, without decimals: "12,345 K $"."""
        number = formatLang(self.env, value / rounding['factor'], digits=0)
        if rounding['suffix']:
            number = '%s %s' % (number, rounding['suffix'])
        return '%s %s' % (currency.symbol, number) if currency.position == 'before' \
            else '%s %s' % (number, currency.symbol)

    @api.model
    def _om_local_datetime(self, value):
        """A UTC datetime of the report in the user's time zone, without tzinfo (for Excel)."""
        value = fields.Datetime.to_datetime(value)
        return fields.Datetime.context_timestamp(self, value).replace(tzinfo=None)

    @api.model
    def _om_header_groups(self, columns):
        """[(label, colspan)] of the header row above the columns, or [] when no column has a group."""
        if not any(c.get('group') for c in columns):
            return []
        groups = []
        for column in columns:
            label = column.get('group') or ''
            if groups and groups[-1][0] == label and label:
                groups[-1][1] += 1
            else:
                groups.append([label, 1])
        return groups

    @api.model
    def _om_filename(self, export, extension):
        name = export['title']
        if export['subtitle']:
            name = '%s - %s' % (name, export['subtitle'])
        name = ''.join(c if c.isalnum() or c in ' -_.()' else '-' for c in name)
        return '%s.%s' % (name, extension)


class ReportOmReportEngineDynamic(models.AbstractModel):
    _name = 'report.om_report_engine.report_dynamic'
    _description = 'Dynamic Report PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        exporter = self.env['om.report.export']
        export = exporter._om_export(data['params'])
        # wkhtmltopdf knows no logical CSS properties: the sides of the language are given to the template
        rtl = self.env['res.lang']._lang_get(self.env.lang or 'en_US').direction == 'rtl'
        return {
            'direction': 'rtl' if rtl else 'ltr',
            'start': 'right' if rtl else 'left',
            'end': 'left' if rtl else 'right',
            'doc_ids': docids,
            'export': export,
            'company': export['company'],
            'header_groups': exporter._om_header_groups(export['columns']),
            'cell': lambda line, column: exporter._om_cell(export, line, column),
            'format_kpi': lambda kpi: exporter._om_kpi_value(export, kpi),
            'numeric': NUMERIC_TYPES,
            'row_class': self._om_row_class,
            'cell_class': self._om_cell_class,
            'printed_on': format_datetime(self.env, datetime.now(), dt_format='short'),
        }

    @api.model
    def _om_row_class(self, line):
        kind = line['kind']
        if kind in ('group', 'leaf') and line.get('has_children'):
            return 'o_omr_group o_omr_group_%s' % min(line['level'], 3)
        return 'o_omr_%s' % kind

    @api.model
    def _om_cell_class(self, line, column):
        classes = []
        if column['type'] in NUMERIC_TYPES:
            classes.append('o_omr_num')
            value = (line.get('values') or {}).get(column['key'])
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value < -0.005:
                classes.append('o_omr_negative')
        return ' '.join(classes)
