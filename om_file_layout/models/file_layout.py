import csv
import io
from datetime import date, datetime

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_round
from odoo.tools.safe_eval import safe_eval

SECTIONS = [('header', 'Header'), ('line', 'Line'), ('footer', 'Footer')]
LINE_ENDINGS = {'crlf': '\r\n', 'lf': '\n'}


class FileLayout(models.Model):
    """ The layout of a file sent out of Odoo, e.g. the salary transfer file of a bank: CSV, fixed width or Excel,
    with a header, one line per record and a footer, each made of columns computed from the records.

    Each layout adds an entry to the Action menu of its model. A model may give the lines of the file itself,
    instead of one line per record, with ``_file_lines(layout)``: the salary transfers of payslips split over
    several bank accounts, for instance.
    """
    _name = 'file.layout'
    _description = 'File Layout'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    model_id = fields.Many2one(
        'ir.model', string='Applies To', required=True, ondelete='cascade', index=True,
        domain=[('transient', '=', False), ('abstract', '=', False)])
    model = fields.Char(related='model_id.model', store=True, index=True)
    file_format = fields.Selection([('csv', 'CSV'), ('fixed', 'Fixed Width'), ('xlsx', 'Excel')],
                                   string='Format', required=True, default='csv')
    csv_separator = fields.Char(string='Separator', default=',', size=1)
    csv_quoting = fields.Selection([('minimal', 'When Needed'), ('all', 'Always'), ('none', 'Never')],
                                   string='Quotes', default='minimal')
    column_titles = fields.Boolean(default=True,
                                   help='Start the lines with a row of the titles of the columns.')
    encoding = fields.Selection([
        ('utf-8', 'UTF-8'),
        ('utf-8-sig', 'UTF-8 with BOM'),
        ('cp1252', 'Windows-1252'),
        ('ascii', 'ASCII'),
    ], required=True, default='utf-8')
    line_ending = fields.Selection([('crlf', 'Windows (CRLF)'), ('lf', 'Unix (LF)')], required=True,
                                   default='crlf')
    file_name = fields.Char(
        required=True, default='{layout}_{date}',
        help='{layout}, {date} (20260630), {datetime} (20260630_1530) and {company} are replaced. The extension '
             'follows the format.')
    extension = fields.Char(help='Leave empty for .csv, .txt or .xlsx.')
    column_ids = fields.One2many('file.layout.column', 'layout_id', string='Columns', copy=True)
    header_column_ids = fields.One2many('file.layout.column', 'layout_id', string='Header',
                                        domain=[('section', '=', 'header')], context={'default_section': 'header'})
    line_column_ids = fields.One2many('file.layout.column', 'layout_id', string='Lines',
                                      domain=[('section', '=', 'line')], context={'default_section': 'line'})
    footer_column_ids = fields.One2many('file.layout.column', 'layout_id', string='Footer',
                                        domain=[('section', '=', 'footer')], context={'default_section': 'footer'})
    action_menu = fields.Boolean(string='In the Action Menu', default=True)
    ref_ir_act_window = fields.Many2one('ir.actions.act_window', readonly=True, copy=False)
    company_id = fields.Many2one('res.company', help='Leave empty to share the layout with all the companies.')
    export_ids = fields.One2many('file.export', 'layout_id', string='Exports')
    export_count = fields.Integer(compute='_compute_export_count')

    def _compute_export_count(self):
        counts = dict(self.env['file.export']._read_group(
            [('layout_id', 'in', self.ids)], ['layout_id'], ['__count']))
        for layout in self:
            layout.export_count = counts.get(layout, 0)

    @api.constrains('file_format', 'csv_separator')
    def _check_separator(self):
        for layout in self:
            if layout.file_format == 'csv' and not layout.csv_separator:
                raise ValidationError(self.env._('The CSV layout %s needs a separator.', layout.name))

    @api.model_create_multi
    def create(self, vals_list):
        layouts = super().create(vals_list)
        layouts._sync_action_menu()
        return layouts

    def write(self, vals):
        result = super().write(vals)
        if {'action_menu', 'name', 'model_id', 'active'} & set(vals):
            self._sync_action_menu()
        return result

    def unlink(self):
        actions = self.sudo().ref_ir_act_window
        result = super().unlink()
        actions.unlink()
        return result

    def _sync_action_menu(self):
        """ The entry of each layout in the Action menu of its model, opening the export wizard. """
        for layout in self.sudo():
            if not (layout.action_menu and layout.active):
                layout.ref_ir_act_window.unlink()
                continue
            values = {
                'name': self.env._('Export: %s', layout.name),
                'res_model': 'file.export.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': repr({'default_layout_id': layout.id}),
                'binding_model_id': layout.model_id.id,
                'binding_type': 'action',
            }
            if layout.ref_ir_act_window:
                layout.ref_ir_act_window.write(values)
            else:
                layout.ref_ir_act_window = self.env['ir.actions.act_window'].create(values)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _get_lines(self, records):
        """ :return: the values each line of the file is computed from, a dict per line """
        self.ensure_one()
        if hasattr(records, '_file_lines'):
            return records._file_lines(self)
        return [{'record': record, 'object': record} for record in records]

    def _base_context(self, records, lines):
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        return {
            'records': records,
            'lines': lines,
            'count': len(lines),
            'total': sum(line.get('amount') or 0.0 for line in lines),
            'today': now.date(),
            'now': now,
            'company': self.env.company,
            'user': self.env.user,
            'layout': self,
        }

    def _render(self, records):
        """ :return: the file as bytes, its lines as text for a preview, and the problems found, as a dict """
        self.ensure_one()
        lines = self._get_lines(records)
        base = self._base_context(records, lines)
        problems = []
        rows = []  # each row: a list of (column, raw value, text)
        columns = {section: self.column_ids.filtered(lambda c, s=section: c.section == s).sorted('sequence')
                   for section, _label in SECTIONS}
        if columns['header']:
            rows.append(self._render_row(columns['header'], base, self.env._('Header'), problems))
        if columns['line'] and self.column_titles and self.file_format != 'fixed':
            rows.append([(column, column.name, column.name) for column in columns['line']])
        for index, line in enumerate(lines, start=1):
            problems.extend(line.get('problems', []))
            context = dict(base, **line, index=index)
            label = self.env._('Line %(index)s (%(record)s)', index=index,
                               record=(line.get('record') or line.get('object') or records[:0]).display_name or index)
            rows.append(self._render_row(columns['line'], context, label, problems))
        if columns['footer']:
            rows.append(self._render_row(columns['footer'], base, self.env._('Footer'), problems))
        content = self._write(rows)
        preview = '\n'.join(self._row_text(row) for row in rows[:30])
        return {'content': content, 'preview': preview, 'problems': problems, 'line_count': len(lines),
                'total': base['total']}

    def _render_row(self, columns, context, label, problems):
        row = []
        for column in columns:
            try:
                value = safe_eval(column.expression or "''", dict(context))
            except Exception as error:  # shown to the user as a problem of the file
                problems.append(self.env._('%(where)s, %(column)s: %(error)s', where=label, column=column.name,
                                           error=error))
                value = False
            text, problem = column._format(value, self.file_format == 'fixed')
            if problem:
                problems.append(self.env._('%(where)s, %(column)s: %(problem)s', where=label, column=column.name,
                                           problem=problem))
            row.append((column, value, text))
        return row

    def _row_text(self, row):
        if self.file_format == 'fixed':
            return ''.join(text for _column, _value, text in row)
        separator = self.csv_separator if self.file_format == 'csv' else '\t'
        return separator.join(text for _column, _value, text in row)

    def _write(self, rows):
        if self.file_format == 'xlsx':
            return self._write_xlsx(rows)
        ending = LINE_ENDINGS[self.line_ending]
        if self.file_format == 'fixed':
            text = ending.join(''.join(text for _column, _value, text in row) for row in rows)
            text += ending if rows else ''
        else:
            buffer = io.StringIO()
            quoting = {'minimal': csv.QUOTE_MINIMAL, 'all': csv.QUOTE_ALL, 'none': csv.QUOTE_NONE}[self.csv_quoting]
            writer = csv.writer(buffer, delimiter=self.csv_separator, quoting=quoting, lineterminator=ending,
                                escapechar='\\' if quoting == csv.QUOTE_NONE else None)
            for row in rows:
                writer.writerow([text for _column, _value, text in row])
            text = buffer.getvalue()
        return text.encode(self.encoding, errors='replace')

    def _write_xlsx(self, rows):
        import xlsxwriter  # only needed for this format
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = workbook.add_worksheet((self.name or 'Sheet')[:31])
        for row_index, row in enumerate(rows):
            for col_index, (column, value, text) in enumerate(row):
                numeric = column.value_type in ('integer', 'decimal') and not column.implied_decimals \
                    and isinstance(value, (int, float)) and not isinstance(value, bool) and text != column.name
                if numeric:
                    sheet.write_number(row_index, col_index, float(text.replace(column.decimal_separator or '.', '.')))
                else:
                    sheet.write_string(row_index, col_index, text)
        workbook.close()
        return buffer.getvalue()

    def _get_file_name(self):
        self.ensure_one()
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        name = (self.file_name or '{layout}').format(
            layout=self.name or '', date=now.strftime('%Y%m%d'), datetime=now.strftime('%Y%m%d_%H%M'),
            company=self.env.company.name or '')
        extension = self.extension or {'csv': 'csv', 'fixed': 'txt', 'xlsx': 'xlsx'}[self.file_format]
        return '%s.%s' % (name.replace('/', '_'), extension.lstrip('.'))

    def action_open_exports(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Exports'),
            'res_model': 'file.export',
            'view_mode': 'list,form',
            'domain': [('layout_id', '=', self.id)],
        }


class FileLayoutColumn(models.Model):
    """ A value of the file: what it holds and how it is written. """
    _name = 'file.layout.column'
    _description = 'File Layout Column'
    _order = 'layout_id, section, sequence, id'

    layout_id = fields.Many2one('file.layout', required=True, ondelete='cascade', index=True)
    section = fields.Selection(SECTIONS, required=True, default='line')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Title', required=True)
    expression = fields.Char(
        string='Value', required=True, default="''",
        help="A Python expression, e.g. record.name, today, count, total, or 'H' for a fixed text. Each line also "
             "reads what its model gives it, e.g. employee, bank and amount for the salary transfers.")
    value_type = fields.Selection([('text', 'Text'), ('integer', 'Integer'), ('decimal', 'Decimal'),
                                   ('date', 'Date')], string='Type', required=True, default='text')
    width = fields.Integer(help='Fixed width: the exact width. Other formats: the longest value allowed, 0 for any.')
    align = fields.Selection([('left', 'Left'), ('right', 'Right')], default='left')
    pad_char = fields.Char(string='Padding', size=1, default=' ', help='e.g. a space, or 0 for the amounts.')
    upper = fields.Boolean(string='Upper Case')
    decimals = fields.Integer(default=2)
    decimal_separator = fields.Char(size=1, default='.')
    implied_decimals = fields.Boolean(help='Write 1500.00 as 150000, as some banks ask.')
    date_format = fields.Char(default='%Y-%m-%d', help='e.g. %d/%m/%Y, %Y%m%d')
    required = fields.Boolean(help='Report a problem when the value is empty.')

    def _format(self, value, fixed):
        """ :return: the value as written in the file, and the problem it has, if any """
        self.ensure_one()
        problem = False
        empty = value is False or value is None or value == ''
        if empty:
            text = ''
            if self.required:
                problem = self.env._('empty')
        elif self.value_type in ('integer', 'decimal'):
            try:
                number = float(value)
            except (TypeError, ValueError):
                return str(value), self.env._('%s is not a number', value)
            if self.value_type == 'integer':
                text = str(int(float_round(number, precision_digits=0)))
            elif self.implied_decimals:
                text = str(int(float_round(number * 10 ** self.decimals, precision_digits=0)))
            else:
                text = ('%.*f' % (self.decimals, float_round(number, precision_digits=self.decimals))).replace(
                    '.', self.decimal_separator or '.')
        elif self.value_type == 'date':
            text = value.strftime(self.date_format or '%Y-%m-%d') if isinstance(value, (date, datetime)) \
                else str(value)
        else:
            text = value.display_name if isinstance(value, models.BaseModel) else str(value)
        text = text.replace('\r', ' ').replace('\n', ' ')
        if self.upper:
            text = text.upper()
        if self.width:
            if len(text) > self.width:
                problem = problem or self.env._('%(value)s is longer than %(width)s', value=text, width=self.width)
                text = text[:self.width]
            if fixed:
                pad = self.pad_char or ' '
                text = text.rjust(self.width, pad) if self.align == 'right' else text.ljust(self.width, pad)
        return text, problem
