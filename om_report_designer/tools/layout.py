"""The layout of a design and its HTML.

A layout is a list of bands, top to bottom. A free band has a height and
elements placed on it in millimetres; a table band lists the lines of a
one2many (or many2many) field of the record, one column per field. The same
HTML serves the PDF, the screen and the preview of the designer, so what the
designer shows is what prints.

Every value of the layout is checked or cast before it reaches the HTML:
numbers are floats, colors match ``#rgb``/``#rrggbb``, choices come from
fixed lists and texts are escaped.
"""
import re
import uuid

from markupsafe import Markup, escape

from odoo import fields, models
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.tools import format_date, format_datetime, formatLang, html2plaintext
from odoo.tools.image import image_data_uri
from odoo.tools.safe_eval import datetime, safe_eval, time

# page sizes in mm, portrait
PAPERS = {
    'A4': (210.0, 297.0),
    'A5': (148.0, 210.0),
    'Letter': (215.9, 279.4),
    'Legal': (215.9, 355.6),
}
# order of the bands on the page; record and table bands repeat per record
BAND_RANK = {'page_header': 0, 'report_header': 1, 'record': 2, 'table': 2, 'report_footer': 3, 'page_footer': 4}
SINGLE_BANDS = ('page_header', 'report_header', 'report_footer', 'page_footer')
ELEMENT_TYPES = ('text', 'field', 'line', 'box', 'image', 'page', 'date')
FORMATS = ('auto', 'number', 'monetary', 'date', 'datetime', 'image')
ALIGNS = ('left', 'center', 'right')
VALIGNS = ('top', 'middle', 'bottom')
COLOR = re.compile(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?')
X2MANY = ('one2many', 'many2many')

# the PDF engine's pages are a padded container, with more padding over the
# header when the company's paper format uses CSS margins: the report's own
# pages must start right at the margins of its paper format
PDF_RESET = Markup(
    '<style>html, body.o_body_pdf { margin: 0 !important; padding: 0 !important; '
    'max-width: none !important; width: auto !important; } '
    'body.o_body_pdf .header, body.o_body_pdf .footer { padding: 0 !important; margin: 0 !important; }</style>')

# the page of a document, shown on the screen; the PDF engine fills the page
# numbers of the header and footer itself
PAGE_SCREEN = {'page': '1', 'pages': '1'}


def page_size(paper, orientation):
    width, height = PAPERS.get(paper) or PAPERS['A4']
    return (height, width) if orientation == 'landscape' else (width, height)


def _number(value, default=0.0, low=0.0, high=2000.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return round(min(max(value, low), high), 2)


def _mm(value):
    return f'{value:g}mm'


def _color(value):
    return value if isinstance(value, str) and COLOR.fullmatch(value) else None


def _choice(value, choices, default=None):
    return value if value in choices else (default if default is not None else choices[0])


def _new_id(prefix):
    return prefix + uuid.uuid4().hex[:8]


def resolve_path(env, model, path):
    """ The fields of ``path`` (``partner_id.country_id.name``) from ``model``,
    or a ValidationError naming the part that does not exist. """
    names = (path or '').split('.')
    result = []
    for name in names:
        model_fields = env[model]._fields
        if not name or name not in model_fields:
            raise ValidationError(env._('The field “%(path)s” does not exist on %(model)s.',
                                        path=path, model=env['ir.model']._get(model).name or model))
        field = model_fields[name]
        result.append(field)
        if field.relational:
            model = field.comodel_name
        elif name != names[-1]:
            raise ValidationError(env._('The field “%(path)s” has no fields after “%(name)s”.', path=path, name=name))
    return result


def check_layout(env, model, layout):
    """ The layout, cleaned: unknown keys dropped, numbers cast, ids given,
    bands sorted. Raises a ValidationError for a field that does not exist. """
    layout = layout if isinstance(layout, dict) else {}
    bands = []
    seen = set()
    for band in layout.get('bands') or []:
        if not isinstance(band, dict) or band.get('kind') not in BAND_RANK:
            continue
        kind = band['kind']
        if kind in SINGLE_BANDS:
            if kind in seen:
                continue
            seen.add(kind)
        clean = {'id': str(band.get('id') or _new_id('b')), 'kind': kind}
        if kind == 'table':
            relation = band.get('relation') or ''
            field = resolve_path(env, model, relation)[-1]
            if '.' in relation or field.type not in X2MANY:
                raise ValidationError(env._('A table lists the lines of a one2many or many2many field, '
                                            'not “%s”.', relation))
            comodel = field.comodel_name
            domain = band.get('domain') or ''
            if domain:
                try:
                    env[comodel].search_count(_eval_domain(env, domain), limit=1)
                except Exception as error:  # noqa: BLE001 the message is shown to the designer
                    raise ValidationError(env._('The line filter of the table “%(name)s” is not valid: %(error)s',
                                                name=field.string, error=error)) from error
            order = band.get('order') or ''
            if order:
                try:
                    env[comodel].search([], order=order, limit=1)
                except Exception as error:  # noqa: BLE001
                    raise ValidationError(env._('The sort order of the table “%(name)s” is not valid: %(error)s',
                                                name=field.string, error=error)) from error
            columns = []
            for column in band.get('columns') or []:
                if not isinstance(column, dict) or not column.get('field'):
                    continue
                resolve_path(env, comodel, column['field'])
                columns.append({
                    'id': str(column.get('id') or _new_id('c')),
                    'field': column['field'],
                    'label': str(column.get('label') or ''),
                    'width': _number(column.get('width'), 25, 3, 1000),
                    'align': _choice(column.get('align'), ALIGNS),
                    'format': _choice(column.get('format'), FORMATS),
                    'digits': None if column.get('digits') in (None, '') else int(_number(column['digits'], 2, 0, 10)),
                    'sum': bool(column.get('sum')),
                })
            clean.update({
                'relation': relation,
                'domain': domain,
                'order': order,
                'x': _number(band.get('x'), 0, 0, 1000),
                'font_size': _number(band.get('font_size'), 9, 4, 72),
                'row_height': _number(band.get('row_height'), 6, 2, 100),
                'header_bg': _color(band.get('header_bg')) or '',
                'header_color': _color(band.get('header_color')) or '',
                'border': bool(band.get('border', True)),
                'stripe': bool(band.get('stripe')),
                'columns': columns,
            })
        else:
            elements = []
            for element in band.get('elements') or []:
                if not isinstance(element, dict) or element.get('type') not in ELEMENT_TYPES:
                    continue
                elements.append(_check_element(env, model, element))
            clean.update({
                'height': _number(band.get('height'), 10, 1, 1000),
                'elements': elements,
            })
        bands.append(clean)
    bands.sort(key=lambda b: BAND_RANK[b['kind']])
    return {'version': 1, 'bands': bands}


def _check_element(env, model, element):
    kind = element['type']
    style = element.get('style') if isinstance(element.get('style'), dict) else {}
    clean = {
        'id': str(element.get('id') or _new_id('e')),
        'type': kind,
        'x': _number(element.get('x')),
        'y': _number(element.get('y')),
        'w': _number(element.get('w'), 30, 0.1),
        'h': _number(element.get('h'), 6, 0.1),
        'style': {
            'font_size': _number(style.get('font_size'), 10, 4, 120),
            'bold': bool(style.get('bold')),
            'italic': bool(style.get('italic')),
            'underline': bool(style.get('underline')),
            'color': _color(style.get('color')) or '',
            'background': _color(style.get('background')) or '',
            'align': _choice(style.get('align'), ALIGNS),
            'valign': _choice(style.get('valign'), VALIGNS, 'middle'),
            'border': bool(style.get('border')),
            'border_color': _color(style.get('border_color')) or '',
            'border_width': _number(style.get('border_width'), 0.3, 0.1, 10),
            'wrap': bool(style.get('wrap')),
        },
    }
    if kind in ('text', 'page'):
        clean['text'] = str(element.get('text') or '')
    if kind in ('field', 'image'):
        source = _choice(element.get('source'), ('record', 'company'))
        clean['source'] = source
        path = element.get('field') or ''
        if kind == 'image' and source == 'company':
            path = path or 'logo'
        if path:
            resolve_path(env, 'res.company' if source == 'company' else model, path)
        elif kind == 'field':
            raise ValidationError(env._('A field element has no field.'))
        clean['field'] = path
    if kind in ('field', 'date'):
        clean['format'] = _choice(element.get('format'), FORMATS)
        clean['digits'] = None if element.get('digits') in (None, '') else int(_number(element['digits'], 2, 0, 10))
    return clean


def _eval_domain(env, domain):
    return safe_eval(domain or '[]', {
        'uid': env.uid,
        'user': env.user,
        'context_today': lambda: fields.Date.context_today(env.user),
        'datetime': datetime,
        'time': time,
    })


class LayoutRenderer:
    """ HTML of a layout for some records, as the current user: fields the
    user may not read stay empty. ``mode`` is ``pdf`` (header and footer in
    the divs the PDF engine repeats on each page, one article per record when
    each record starts a page) or ``html`` (one block, for the screen). """

    def __init__(self, design, layout, records, mode='html'):
        self.design = design
        self.layout = layout
        self.records = records
        self.env = records.env
        self.mode = mode
        self.width = design._printable_width()
        self.company = self.env.company

    # ------------------------------------------------------------------
    # document
    # ------------------------------------------------------------------

    def render(self):
        bands = self.layout.get('bands') or []
        page_header = [b for b in bands if b['kind'] == 'page_header']
        page_footer = [b for b in bands if b['kind'] == 'page_footer']
        report_header = [b for b in bands if b['kind'] == 'report_header']
        report_footer = [b for b in bands if b['kind'] == 'report_footer']
        body = [b for b in bands if b['kind'] in ('record', 'table')]

        records = list(self.records) or [self.records]
        if self.mode == 'pdf':
            if self.design.page_break:
                groups = [[record] for record in records]
            else:
                groups = [records]
            parts = []
            for index, group in enumerate(groups):
                first, last = index == 0, index == len(groups) - 1
                content = []
                if first:
                    content += [self._band(b, group[0]) for b in report_header]
                for record in group:
                    content += [self._band(b, record) for b in body]
                if last:
                    content += [self._band(b, group[-1]) for b in report_footer]
                record = group[0]
                parts.append(Markup('<div class="header">%s</div>') % self._doc(
                    [self._band(b, record) for b in page_header]))
                article = Markup('<div class="article" data-oe-lang="%s"%s>%s</div>') % (
                    self.env.lang or '',
                    Markup(' data-oe-model="%s" data-oe-id="%s"') % (record._name, record.id)
                    if self.design.page_break and record else '',
                    self._doc(content),
                )
                parts.append(article)
                parts.append(Markup('<div class="footer">%s</div>') % self._doc(
                    [self._band(b, record) for b in page_footer]))
            return Markup('').join(parts)

        content = [self._band(b, records[0]) for b in page_header + report_header]
        for index, record in enumerate(records):
            bands_html = Markup('').join(self._band(b, record) for b in body)
            content.append(Markup('<div class="o_om_rd_record%s">%s</div>') % (
                ' o_om_rd_break' if index and self.design.page_break else '', bands_html))
        content += [self._band(b, records[-1]) for b in report_footer + page_footer]
        return self._doc(content)

    def _doc(self, content):
        return Markup('%s<div class="o_om_rd_doc" style="width:%s">%s</div>') % (
            PDF_RESET if self.mode == 'pdf' else '', _mm(self.width), Markup('').join(content))

    def _band(self, band, record):
        if band['kind'] == 'table':
            return self._table(band, record)
        elements = Markup('').join(self._element(element, record) for element in band['elements'])
        return Markup('<div class="o_om_rd_band" style="height:%s">%s</div>') % (_mm(band['height']), elements)

    # ------------------------------------------------------------------
    # elements
    # ------------------------------------------------------------------

    def _element(self, element, record):
        style = element['style']
        kind = element['type']
        outer = [f"left:{_mm(element['x'])}", f"top:{_mm(element['y'])}",
                 f"width:{_mm(element['w'])}", f"height:{_mm(element['h'])}"]
        if kind == 'line':
            outer.append(f"background-color:{style['color'] or '#000000'}")
            return Markup('<div class="o_om_rd_el o_om_rd_line" style="%s"></div>') % ';'.join(outer)
        if style['background']:
            outer.append(f"background-color:{style['background']}")
        if style['border'] or kind == 'box':
            outer.append(f"border:{_mm(style['border_width'])} solid {style['border_color'] or '#000000'}")
        if kind == 'box':
            return Markup('<div class="o_om_rd_el o_om_rd_box" style="%s"></div>') % ';'.join(outer)

        cell = [f"vertical-align:{style['valign']}", f"text-align:{style['align']}",
                f"font-size:{style['font_size']:g}pt"]
        if style['bold']:
            cell.append('font-weight:bold')
        if style['italic']:
            cell.append('font-style:italic')
        if style['underline']:
            cell.append('text-decoration:underline')
        if style['color']:
            cell.append(f"color:{style['color']}")
        cell.append('white-space:normal' if style['wrap'] else 'white-space:nowrap')

        content = self._content(element, record)
        return Markup(
            '<div class="o_om_rd_el" style="%s"><div class="o_om_rd_tbl"><div class="o_om_rd_cell" style="%s">'
            '%s</div></div></div>'
        ) % (';'.join(outer), ';'.join(cell), content)

    def _content(self, element, record):
        kind = element['type']
        if kind == 'text':
            return self._text(element['text'])
        if kind == 'page':
            text = escape(element['text'] or '{page} / {pages}')
            if self.mode == 'pdf':
                values = {'page': Markup('<span class="page"></span>'), 'pages': Markup('<span class="topage"></span>')}
            else:
                values = PAGE_SCREEN
            for key, value in values.items():
                text = text.replace('{%s}' % key, value)
            return Markup(text)
        if kind == 'date':
            now = fields.Datetime.now()
            if element.get('format') == 'datetime':
                return format_datetime(self.env, now, dt_format='short')
            return format_date(self.env, fields.Datetime.context_timestamp(self.env.user, now).date())
        if kind == 'image':
            target = self.company if element.get('source') == 'company' else record
            return self._image(self._raw(target, element.get('field') or 'logo'), element['w'], element['h'])
        # field
        target = self.company if element.get('source') == 'company' else record
        if element.get('format') == 'image':
            return self._image(self._raw(target, element['field']), element['w'], element['h'])
        return self._text(self.value(target, element['field'], element.get('format'), element.get('digits')))

    @staticmethod
    def _image(value, width, height):
        # the format Image can be chosen on any field: only a binary value is a picture
        if not value or isinstance(value, (str, int, float, models.BaseModel)):
            return ''
        return Markup('<img src="%s" alt="" style="max-width:%s;max-height:%s"/>') % (
            image_data_uri(value), _mm(width), _mm(height))

    @staticmethod
    def _text(value):
        if not value:
            return ''
        return Markup('<br/>').join(escape(line) for line in str(value).split('\n'))

    # ------------------------------------------------------------------
    # values
    # ------------------------------------------------------------------

    def _walk(self, record, path):
        """ The records holding the last field of ``path``, and that field. """
        names = path.split('.')
        records = record
        for name in names[:-1]:
            records = records.mapped(name)
        return records, records._fields.get(names[-1])

    def _raw(self, record, path):
        try:
            records, field = self._walk(record, path)
            if not field or not records:
                return None
            return records[:1][field.name] or None
        except (AccessError, MissingError, KeyError):
            return None

    def value(self, record, path, fmt='auto', digits=None):
        """ The value of ``path`` on ``record`` as text, formatted for the
        language of the user; values of several records joined by commas. """
        if not record or not path:
            return ''
        try:
            records, field = self._walk(record, path)
            if not field:
                return ''
            return ', '.join(filter(None, (self._format(rec, field, fmt, digits) for rec in records)))
        except (AccessError, MissingError):
            return ''

    def _format(self, record, field, fmt='auto', digits=None):
        value = record[field.name]
        kind = field.type
        env = self.env
        if field.relational:
            return ', '.join(value.mapped('display_name'))
        if kind == 'boolean':
            return '✓' if value else ''
        if kind in ('integer', 'float', 'monetary'):
            return self._number(record, field, value, fmt, digits)
        if not value:
            return ''
        if kind == 'selection':
            return dict(field._description_selection(env)).get(value, value)
        if kind == 'date':
            return format_date(env, value)
        if kind == 'datetime':
            if fmt == 'date':
                return format_date(env, fields.Datetime.context_timestamp(record, value).date())
            return format_datetime(env, value, dt_format='short')
        if kind == 'html':
            return html2plaintext(value)
        if kind == 'binary':
            return ''
        return str(value)

    def _number(self, record, field, value, fmt='auto', digits=None):
        env = self.env
        if fmt == 'monetary' or (field.type == 'monetary' and fmt == 'auto'):
            return formatLang(env, value, currency_obj=self._currency(record, field))
        if digits is None:
            if field.type == 'integer':
                digits = 0
            else:
                field_digits = field.get_digits(env)
                digits = field_digits[1] if field_digits else 2
        return formatLang(env, value, digits=digits)

    def _currency(self, record, field):
        name = field.get_currency_field(record) if field.type == 'monetary' else None
        if not name:
            name = 'currency_id' if 'currency_id' in record._fields else None
        currency = record[name] if name else None
        return currency or self.company.currency_id

    # ------------------------------------------------------------------
    # tables
    # ------------------------------------------------------------------

    def _lines(self, band, record):
        lines = record[band['relation']]
        if band.get('domain'):
            lines = lines.filtered_domain(_eval_domain(self.env, band['domain']))
        if band.get('order') and lines:
            lines = lines.search([('id', 'in', lines.ids)], order=band['order'])
        return lines

    def _table(self, band, record):
        columns = band['columns']
        if not columns:
            return Markup('')
        width = sum(c['width'] for c in columns)
        style = [f"width:{_mm(width)}", f"margin-left:{_mm(band['x'])}", f"font-size:{band['font_size']:g}pt"]
        head_style = []
        if band['header_bg']:
            head_style.append(f"background-color:{band['header_bg']}")
        if band['header_color']:
            head_style.append(f"color:{band['header_color']}")
        classes = 'o_om_rd_table' + (' o_om_rd_bordered' if band['border'] else '') + (
            ' o_om_rd_striped' if band['stripe'] else '')
        row_height = _mm(band['row_height'])

        colgroup = Markup('').join(Markup('<col style="width:%s"/>') % _mm(c['width']) for c in columns)
        head = Markup('').join(
            Markup('<th style="text-align:%s;height:%s">%s</th>') % (c['align'], row_height, c['label'])
            for c in columns)

        lines = self._lines(band, record)
        rows = []
        for line in lines:
            cells = Markup('').join(
                Markup('<td style="text-align:%s;height:%s">%s</td>') % (
                    c['align'], row_height, self._cell(line, c)) for c in columns)
            rows.append(Markup('<tr>%s</tr>') % cells)

        if any(c['sum'] for c in columns):
            cells = []
            for c in columns:
                cells.append(Markup('<td style="text-align:%s;height:%s">%s</td>') % (
                    c['align'], row_height, self._total(lines, c) if c['sum'] else ''))
            rows.append(Markup('<tr class="o_om_rd_total">%s</tr>') % Markup('').join(cells))

        return Markup(
            '<table class="%s" style="%s"><colgroup>%s</colgroup><thead><tr style="%s">%s</tr></thead>'
            '<tbody>%s</tbody></table>'
        ) % (classes, ';'.join(style), colgroup, ';'.join(head_style), head, Markup('').join(rows))

    def _cell(self, line, column):
        if column['format'] == 'image':
            return self._image(self._raw(line, column['field']), column['width'] - 2, 30)
        return self._text(self.value(line, column['field'], column['format'], column['digits']))

    def _total(self, lines, column):
        if not lines:
            return ''
        try:
            records, field = self._walk(lines, column['field'])
        except (AccessError, MissingError):
            return ''
        if not field or field.type not in ('integer', 'float', 'monetary'):
            return ''
        if not records:
            return ''
        total = sum(records.mapped(field.name))
        return self._number(records[:1], field, total, column['format'], column['digits'])
