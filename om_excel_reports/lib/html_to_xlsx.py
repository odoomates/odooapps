# Part of Odoo2XL - Odoo Excel Reports (om_excel_reports). License: LGPL-3.
#
# Server-side converter: Odoo QWeb HTML report  ->  .xlsx workbook.
#
# The conversion rules (sheet per ``.article``, numeric/date typing, totals,
# frozen header, filters, "All lines" sheet ...) follow the behaviour of the
# Odoo2XL browser extension by Odoo Mates (https://github.com/odoomates/odoo2xl),
# re-implemented in Python so that the export runs inside Odoo and nothing
# leaves the server.
#
# This file is deliberately free of any ``odoo`` import so that it can be unit
# tested on its own.

import copy
import datetime
import io
import re
from functools import lru_cache

import xlsxwriter
from lxml import html as lxml_html

__all__ = ['ConverterOptions', 'convert_report_html']

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

SKIP_TAGS = {'script', 'style', 'img', 'svg', 'noscript', 'head', 'meta', 'link', 'canvas', 'video', 'audio'}
BLOCK_TAGS = {
    'div', 'p', 'ul', 'ol', 'li', 'tr', 'table', 'section', 'article', 'header', 'footer',
    'main', 'address', 'blockquote', 'pre', 'hr', 'dl', 'dt', 'dd', 'thead', 'tbody',
    'tfoot', 'form', 'fieldset', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
}
HEADINGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
BOLD_TAGS = {'th', 'strong', 'b'} | HEADINGS
BOLD_CLASSES = {'fw-bold', 'fw-bolder', 'o_bold', 'font-weight-bold', 'fw-semibold'}
DROP_CLASSES = {'header', 'footer', 'o_report_layout_header', 'o_footer'}
MAX_COLSPAN = 20
MAX_WIDTH = 60
DEFAULT_WIDTH = 8
FREEZE_LIMIT = 25
SHEET_BAD_CHARS = re.compile(r'[\[\]:*?/\\]')
WS = re.compile(r'[ \t\r\n\f\v]+')
ZERO_WIDTH = dict.fromkeys(map(ord, '﻿​‌‍'), None)
NEG_STYLE = re.compile(r'display\s*:\s*none|visibility\s*:\s*hidden', re.I)
SHOW_CLASS = re.compile(
    r'^d-(?:(?:sm|md|lg|xl|xxl)-)?(?:block|inline|inline-block|flex|inline-flex|table|table-cell|table-row|grid)$'
    r'|^d-print-(?!none)'
)
WHITE_STYLE = re.compile(r'color\s*:\s*(?:white|#fff(?:fff)?|transparent|rgba?\(\s*255\s*,\s*255\s*,\s*255)', re.I)
BOLD_STYLE = re.compile(r'font-weight\s*:\s*(bold|bolder|[6-9]00)', re.I)
PADDING_STYLE = re.compile(r'(?:padding|margin)-(?:left|inline-start)\s*:\s*([\d.]+)\s*(px|em|rem)', re.I)
TEXT_COLUMN = re.compile(
    r'(?:^|\W)(?:code|ref|reference|account|vat|trn|tax\s*id|phone|mobile|tel|iban|bic|swift|sku|barcode|'
    r'zip|postcode|postal|serial|lot|number|no\.?|n°|invoice|barcode)(?:$|\W)', re.I)
QTY_COLUMN = re.compile(r'qty|quant|ordered|delivered|demand|done|reserved|uom|units?', re.I)
AMOUNT_COLUMN = re.compile(r'amount|total|price|balance|debit|credit|subtotal|untaxed', re.I)


class ConverterOptions:
    """Locale / presentation options of the conversion."""

    def __init__(self, decimal_point='.', thousands_sep=',', date_format='%m/%d/%Y', title='Report'):
        self.decimal_point = decimal_point or '.'
        self.thousands_sep = thousands_sep or ''
        self.date_format = date_format or '%m/%d/%Y'
        self.title = title or 'Report'


# --------------------------------------------------------------------------
# DOM helpers
# --------------------------------------------------------------------------

def _tag(el):
    return el.tag.lower() if isinstance(el.tag, str) else ''


def _classes(el):
    return (el.get('class') or '').split()


def is_hidden(el):
    """True if ``el`` would not be visible on the printed report."""
    tag = _tag(el)
    if not tag or tag in SKIP_TAGS:
        return True
    cls = _classes(el)
    if 'o_hidden' in cls or 'd-print-none' in cls:
        return True
    if 'd-none' in cls and not any(SHOW_CLASS.match(c) for c in cls):
        return True
    style = el.get('style')
    if style and NEG_STYLE.search(style):
        return True
    return False


def is_indent_filler(el):
    """Spans made of white dots, used by some reports to indent labels."""
    if _tag(el) != 'span':
        return False
    style = el.get('style') or ''
    if not WHITE_STYLE.search(style):
        return False
    txt = ''.join(el.itertext()).replace('\xa0', '').strip()
    return bool(txt) and set(txt) <= {'.'}


def _ws(text):
    return WS.sub(' ', text) if text else ''


def _walk_text(el, out):
    if el.text:
        out.append(_ws(el.text))
    for ch in el:
        if isinstance(ch.tag, str) and not is_hidden(ch) and not is_indent_filler(ch):
            tag = _tag(ch)
            if tag == 'br':
                out.append('\n')
            else:
                block = tag in BLOCK_TAGS
                if block:
                    out.append('\n')
                _walk_text(ch, out)
                if block:
                    out.append('\n')
        if ch.tail:
            out.append(_ws(ch.tail))


def get_text(el):
    """Visible text of an element; <br> and block elements become line breaks."""
    out = []
    _walk_text(el, out)
    raw = ''.join(out).translate(ZERO_WIDTH).replace('\xa0', ' ')
    lines = [line.strip() for line in raw.split('\n')]
    return '\n'.join(line for line in lines if line)


def text_of_nodes(first_text, nodes):
    """Visible text of a text prefix followed by sibling nodes (with tails)."""
    wrapper = lxml_html.Element('div')
    wrapper.text = first_text
    for node in nodes:
        wrapper.append(copy.deepcopy(node))
    return get_text(wrapper)


def has_visible_descendant(el, tags):
    for d in el.iterdescendants():
        if isinstance(d.tag, str) and _tag(d) in tags and not _is_hidden_chain(d, el):
            return True
    return False


def _is_hidden_chain(el, root):
    node = el
    while node is not None and node is not root:
        if is_hidden(node):
            return True
        node = node.getparent()
    return False


def element_is_bold(el):
    if _tag(el) in BOLD_TAGS:
        return True
    if BOLD_CLASSES.intersection(_classes(el)):
        return True
    style = el.get('style')
    return bool(style and BOLD_STYLE.search(style))


def _bold_state(el, inherited):
    """Return (has_text, all_text_bold) for the content of ``el``."""
    bold = inherited or element_is_bold(el)
    has_text, all_bold = False, True
    if el.text and el.text.strip():
        has_text = True
        all_bold = all_bold and bold
    for ch in el:
        if isinstance(ch.tag, str) and not is_hidden(ch) and not is_indent_filler(ch):
            h, a = _bold_state(ch, bold)
            has_text = has_text or h
            all_bold = all_bold and a
        if ch.tail and ch.tail.strip():
            has_text = True
            all_bold = all_bold and bold
    return has_text, all_bold


def cell_is_bold(el):
    has_text, all_bold = _bold_state(el, False)
    return has_text and all_bold


def indent_level(el):
    """Indentation depth of a cell (white dot pairs + left padding/margin)."""
    level = 0
    dots = 0
    for sp in el.iter('span'):
        if is_indent_filler(sp):
            dots += len(''.join(sp.itertext()).replace('\xa0', '').strip())
    level += dots // 2
    for node in (el, *list(el)[:1]):
        style = node.get('style') if isinstance(node.tag, str) else None
        m = style and PADDING_STYLE.search(style)
        if m:
            px = float(m.group(1)) * (16 if m.group(2) in ('em', 'rem') else 1)
            level += int(px // 20)
            break
    return level


def align_of(el):
    cls = _classes(el)
    if 'text-end' in cls or 'text-right' in cls:
        return 'right'
    if 'text-center' in cls:
        return 'center'
    return None


# --------------------------------------------------------------------------
# Value detection
# --------------------------------------------------------------------------

@lru_cache(maxsize=32)
def _number_regex(dp, ts):
    d = re.escape(dp)
    if ts is None or ts == '':
        group = None
    elif ts.strip() == '':
        group = '[   ]'
    else:
        group = re.escape(ts)
    if group:
        integer = r'(?:\d{1,3}(?:%s\d{3})+|\d+)' % group
    else:
        integer = r'\d+'
    return re.compile(r'^(?P<int>%s)(?:%s(?P<frac>\d+))?$' % (integer, d)), group


def parse_number(text, dp, ts):
    """Parse a localised number. Returns (value, decimals, grouped) or None."""
    s = text.strip().replace('−', '-').replace('–', '-').replace('\xa0', ' ')
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg, s = True, s[1:-1].strip()
    if s.endswith('-'):
        neg, s = True, s[:-1].strip()
    if s.startswith('-'):
        neg, s = True, s[1:].strip()
    elif s.startswith('+'):
        s = s[1:].strip()
    if not s or not s[0].isdigit():
        return None
    regex, group = _number_regex(dp, ts)
    if group and ts.strip() == '':
        s = s.replace(' ', ' ')
    m = regex.match(s)
    if not m:
        return None
    integer, frac = m.group('int'), m.group('frac')
    grouped = False
    if group:
        stripped = re.sub(group, '', integer)
        grouped = stripped != integer
        integer = stripped
    if len(integer) > 1 and integer.startswith('0'):
        return None  # codes such as 00123 stay text
    value = float(integer + ('.' + frac if frac else ''))
    return (-value if neg else value), (len(frac) if frac else 0), grouped


@lru_cache(maxsize=32)
def _date_regexes(fmt):
    tokens = {
        '%d': r'(?P<d>\d{1,2})', '%e': r'\s?(?P<d>\d{1,2})', '%m': r'(?P<m>\d{1,2})',
        '%Y': r'(?P<Y>\d{4})', '%y': r'(?P<y>\d{2})',
    }
    parts, i, ok = [], 0, True
    while i < len(fmt):
        if fmt[i] == '%' and i + 1 < len(fmt):
            tok = fmt[i:i + 2]
            if tok in tokens:
                parts.append(tokens[tok])
            elif tok == '%%':
                parts.append('%')
            else:
                ok = False
                break
            i += 2
        else:
            parts.append(re.escape(fmt[i]))
            i += 1
    time_re = r'(?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?(?:\s*(?P<ap>[AaPp][Mm]))?'
    iso = r'(?P<Y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})'
    regexes = []
    if ok:
        regexes.append(''.join(parts))
    regexes.append(iso)
    return tuple((re.compile('^%s$' % r), re.compile('^%s[ T]%s$' % (r, time_re))) for r in regexes)


def parse_date(text, fmt):
    """Return ('date'|'datetime', value) or None."""
    s = text.strip()
    if len(s) < 8 or len(s) > 30:
        return None
    for date_re, dt_re in _date_regexes(fmt):
        for regex, has_time in ((date_re, False), (dt_re, True)):
            m = regex.match(s)
            if not m:
                continue
            g = m.groupdict()
            try:
                year = int(g['Y']) if g.get('Y') else 2000 + int(g['y'])
                day = datetime.date(year, int(g['m']), int(g['d']))
                if not has_time:
                    return 'date', day
                hour = int(g['H'])
                ap = (g.get('ap') or '').lower()
                if ap == 'pm' and hour < 12:
                    hour += 12
                elif ap == 'am' and hour == 12:
                    hour = 0
                return 'datetime', datetime.datetime.combine(
                    day, datetime.time(hour, int(g['M']), int(g.get('S') or 0)))
            except (ValueError, TypeError):
                return None
    return None


def _quote(text):
    return '"%s"' % text.replace('"', '').replace('\\', '')


def number_format(decimals, grouped, prefix='', suffix='', signed_sections=False):
    base = ('#,##0' if grouped else '0') + ('.' + '0' * decimals if decimals else '')
    pos = (_quote(prefix) if prefix else '') + base + (_quote(suffix) if suffix else '')
    return '%s;-%s' % (pos, pos) if signed_sections else pos


class Cell:
    __slots__ = ('value', 'kind', 'fmt', 'bold', 'align', 'indent', 'wrap', 'orig',
                 'decimals', 'grouped', 'size', 'nowidth')

    def __init__(self, value=None, kind='text', fmt=None, bold=False, align=None, indent=0,
                 wrap=False, orig='', decimals=0, grouped=False, size=None, nowidth=False):
        self.value = value
        self.kind = kind          # text | number | percent | date | datetime
        self.fmt = fmt
        self.bold = bold
        self.align = align
        self.indent = indent
        self.wrap = wrap
        self.orig = orig
        self.decimals = decimals
        self.grouped = grouped
        self.size = size
        self.nowidth = nowidth

    @property
    def empty(self):
        return self.value is None or self.value == ''


def classify_cell(el, header, opts):
    """Turn a table cell (or any element) into a typed :class:`Cell`."""
    text = get_text(el)
    cell = Cell(value=text or None, kind='text', orig=text, bold=cell_is_bold(el),
                align=align_of(el), indent=indent_level(el), wrap='\n' in text)
    if not text:
        cell.value = None
        return cell
    header = header or ''
    dp, ts = opts.decimal_point, opts.thousands_sep

    # Monetary values (Odoo wraps the amount in span.oe_currency_value).
    amounts = [s for s in el.iter('span') if 'oe_currency_value' in _classes(s) and not is_hidden(s)]
    if len(amounts) == 1:
        amount_text = get_text(amounts[0])
        rest = text.replace(amount_text, '', 1).strip()
        neg_prefix = bool(re.search(r'[-−]', rest))
        symbol = re.sub(r'[-−()\s]', '', rest) if rest else ''
        if len(symbol) <= 5 and not re.search(r'[\d%]', symbol):
            parsed = parse_number(amount_text, dp, ts)
            if parsed:
                value, decimals, _grouped = parsed
                if neg_prefix and value > 0:
                    value = -value
                before = (not symbol) or text.replace('-', '').replace('−', '').strip().startswith(symbol)
                cell.value, cell.kind = value, 'number'
                cell.decimals, cell.grouped = decimals, True
                if symbol:
                    cell.fmt = number_format(decimals, True, prefix=symbol + ' ' if before else '',
                                             suffix='' if before else ' ' + symbol, signed_sections=True)
                else:
                    cell.fmt = number_format(decimals, True)
                return cell
        return cell

    if TEXT_COLUMN.search(header) and '%' not in header:
        return cell

    # Percentages.
    pct_match = re.match(r'^(.*?)\s*%$', text)
    if pct_match or '%' in header:
        body = pct_match.group(1) if pct_match else text
        parsed = parse_number(body, dp, ts)
        if parsed and (pct_match or not re.search(r'[a-zA-Z]', text)):
            value, decimals, _g = parsed
            cell.value, cell.kind = value / 100.0, 'percent'
            cell.decimals = decimals
            cell.fmt = '0%s%%' % ('.' + '0' * decimals if decimals else '')
            return cell

    # Dates / date-times.
    dated = parse_date(text, opts.date_format)
    if dated:
        cell.kind, cell.value = dated
        cell.fmt = 'yyyy-mm-dd' if cell.kind == 'date' else 'yyyy-mm-dd hh:mm'
        return cell

    # Plain numbers.
    parsed = parse_number(text, dp, ts)
    if parsed:
        value, decimals, grouped = parsed
        cell.value, cell.kind, cell.decimals, cell.grouped = value, 'number', decimals, grouped
        cell.fmt = number_format(decimals, grouped)
        return cell

    # Quantities with a unit ("10.00 Units").
    m = re.match(r'^(?P<num>[(\-−+]?\d[\d.,\s  \']*)\s+(?P<unit>[^\d\s%(][^\d]{0,19})$', text)
    if m:
        parsed = parse_number(m.group('num'), dp, ts)
        if parsed and (parsed[1] > 0 or QTY_COLUMN.search(header)):
            value, decimals, grouped = parsed
            cell.value, cell.kind, cell.decimals, cell.grouped = value, 'number', decimals, grouped
            cell.fmt = number_format(decimals, grouped, suffix=' ' + m.group('unit').strip())
            return cell
    return cell


# --------------------------------------------------------------------------
# Sheet model
# --------------------------------------------------------------------------

class TableInfo:
    def __init__(self):
        self.header_row = None   # absolute row index of the header (last header row)
        self.first_row = 0
        self.last_row = 0
        self.offset = 0
        self.width = 0
        self.names = []          # lower-cased header text per column
        self.n_data = 0

    @property
    def has_header(self):
        return self.header_row is not None


class Sheet:
    def __init__(self, title):
        self.title = title
        self.cells = {}
        self.merges = []
        self.row = 0
        self.tables = []
        self.freeze_row = None
        self.filter = None   # (r1, c1, r2, c2)
        self.name = None

    def put(self, r, c, cell):
        self.cells[(r, c)] = cell

    @property
    def main_table(self):
        best = None
        for t in self.tables:
            if t.has_header and t.n_data:
                if best is None or t.n_data * t.width > best.n_data * best.width:
                    best = t
        return best


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------

class Converter:
    def __init__(self, opts):
        self.opts = opts

    # -- document ------------------------------------------------------
    def convert(self, html_source):
        if isinstance(html_source, bytes):
            doc = lxml_html.document_fromstring(html_source)
        else:
            doc = lxml_html.document_fromstring(html_source.encode('utf-8'))
        for el in list(doc.iter()):
            if isinstance(el.tag, str) and DROP_CLASSES.intersection(_classes(el)):
                if el.getparent() is not None:
                    el.drop_tree()
        articles = doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' article ')]")
        # Keep outermost articles only.
        articles = [a for a in articles
                    if not any(anc in articles for anc in a.iterancestors())]
        if not articles:
            main = doc.xpath('//main') or doc.xpath('//body')
            articles = main[:1] or [doc]
        sheets = []
        for i, art in enumerate(articles, 1):
            sheet = Sheet(self._sheet_title(art) or ('%s %d' % (self.opts.title, i) if len(articles) > 1
                                                       else self.opts.title))
            self._walk_children(art, sheet)
            if sheet.cells:
                sheets.append(sheet)
        if not sheets:
            raise ValueError('The report has no content that can be exported to Excel.')
        for sh in sheets:
            self._finalise(sh)
        combined = self._all_lines(sheets)
        if combined:
            sheets.insert(0, combined)
        self._name_sheets(sheets)
        return sheets

    def _sheet_title(self, art):
        for el in art.iter('h1', 'h2', 'h3'):
            if is_hidden(el) or _is_hidden_chain(el, art):
                continue
            text = get_text(el).replace('\n', ' ').strip()
            if text:
                return text.split(':', 1)[1].strip() if ':' in text and text.split(':', 1)[1].strip() else text
        return None

    @staticmethod
    def _name_sheets(sheets):
        used = set()
        for i, sh in enumerate(sheets, 1):
            base = SHEET_BAD_CHARS.sub(' ', sh.title or 'Report %d' % i).strip().strip("'")[:31] or 'Report %d' % i
            name, n = base, 1
            while name.lower() in used:
                n += 1
                suffix = ' %d' % n
                name = base[:31 - len(suffix)] + suffix
            used.add(name.lower())
            sh.name = name

    # -- layout walk ---------------------------------------------------
    def _walk_children(self, node, sheet):
        run_text = node.text or ''
        run_nodes = []

        def flush():
            nonlocal run_text, run_nodes
            text = text_of_nodes(run_text, run_nodes) if (run_nodes or run_text.strip()) else ''
            if text:
                self._emit_text(sheet, text)
            run_text, run_nodes = '', []

        for ch in node:
            tag = _tag(ch)
            if not tag or is_hidden(ch):
                tail = ch.tail or ''
                if run_nodes:
                    run_nodes[-1].tail = (run_nodes[-1].tail or '') + tail
                else:
                    run_text += tail
                continue
            if tag == 'table':
                flush()
                self._add_table(ch, sheet)
                run_text = ch.tail or ''
            elif tag in HEADINGS:
                flush()
                self._add_heading(ch, sheet)
                run_text = ch.tail or ''
            elif tag in BLOCK_TAGS:
                flush()
                self._add_block(ch, sheet)
                run_text = ch.tail or ''
            else:
                run_nodes.append(copy.deepcopy(ch))
        flush()

    def _add_block(self, el, sheet):
        if self._is_bootstrap_row(el):
            self._add_columns(el, sheet)
        elif has_visible_descendant(el, BLOCK_TAGS - {'li'}) or has_visible_descendant(el, {'table'} | HEADINGS):
            self._walk_children(el, sheet)
        else:
            text = get_text(el)
            if not text:
                return
            pair = self._label_value(el)
            if pair:
                self._emit_cells(sheet, [pair[0], pair[1]])
            else:
                self._emit_text(sheet, text, bold=cell_is_bold(el))

    @staticmethod
    def _is_bootstrap_row(el):
        if 'row' not in _classes(el):
            return False
        kids = [c for c in el if isinstance(c.tag, str) and not is_hidden(c)]
        return bool(kids) and all(any(k == 'col' or k.startswith('col-') for k in _classes(c)) for c in kids)

    def _add_columns(self, row_el, sheet):
        cells = []
        for col in row_el:
            if not isinstance(col.tag, str) or is_hidden(col):
                continue
            if has_visible_descendant(col, {'table'}):
                # Tables inside a bootstrap row: flatten vertically.
                self._walk_children(col, sheet)
                continue
            cells.extend(self._pairs_from(col))
        self._emit_cells(sheet, cells)

    def _pairs_from(self, el):
        """Return a list of cells: (label, value) pairs for strong/b labels, else one text cell."""
        has_label = any(_tag(c) in ('strong', 'b') and not is_hidden(c) and get_text(c) for c in el)
        if not has_label:
            text = get_text(el)
            return [self._make_cell(text)] if text else []
        # Walk the top-level content of el; split at every direct strong child.
        out = []
        prefix = el.text or ''
        pending_label, pending_nodes, pending_text = None, [], ''

        def close():
            nonlocal pending_label, pending_nodes, pending_text
            if pending_label is not None:
                value = text_of_nodes(pending_text, pending_nodes)
                out.append(self._make_cell(pending_label, bold=True))
                out.append(self._value_cell(value) if value else Cell())
            pending_label, pending_nodes, pending_text = None, [], ''

        lead = text_of_nodes(prefix, [])
        if lead:
            out.append(self._make_cell(lead))
        for ch in el:
            if not isinstance(ch.tag, str):
                continue
            if _tag(ch) in ('strong', 'b') and not is_hidden(ch) and get_text(ch):
                close()
                pending_label = get_text(ch)
                pending_text = ch.tail or ''
            elif pending_label is not None:
                pending_nodes.append(ch)
            else:
                text = get_text(ch)
                if text:
                    out.append(self._make_cell(text))
                if ch.tail and ch.tail.strip():
                    out.append(self._make_cell(_ws(ch.tail).strip()))
        close()
        return out

    def _label_value(self, el):
        """('Label:', 'value') for elements that start with a <strong>/<b> label."""
        if (el.text or '').strip():
            return None
        kids = [c for c in el if isinstance(c.tag, str)]
        if not kids or _tag(kids[0]) not in ('strong', 'b') or is_hidden(kids[0]):
            return None
        label = get_text(kids[0])
        if not label:
            return None
        value = text_of_nodes(kids[0].tail or '', kids[1:])
        if not value:
            return None
        return self._make_cell(label, bold=True), self._value_cell(value)

    def _make_cell(self, text, bold=False):
        return Cell(value=text, kind='text', orig=text, bold=bold, wrap='\n' in text)

    def _value_cell(self, text):
        """Typed cell (number, date ...) for a free-standing value."""
        span = lxml_html.Element('span')
        span.text = text
        return classify_cell(span, '', self.opts)

    def _emit_text(self, sheet, text, bold=False):
        cell = self._make_cell(text, bold=bold)
        cell.nowidth = '\n' not in text
        sheet.put(sheet.row, 0, cell)
        sheet.row += 1

    def _emit_cells(self, sheet, cells):
        cells = list(cells)
        if not cells or all(c.empty for c in cells):
            return
        for i, c in enumerate(cells):
            sheet.put(sheet.row, i, c)
        sheet.row += 1

    def _add_heading(self, el, sheet):
        text = get_text(el).replace('\n', ' ')
        if not text:
            return
        cell = Cell(value=text, kind='text', orig=text, bold=True, nowidth=True,
                    size=14 if _tag(el) in ('h1', 'h2') else None)
        sheet.put(sheet.row, 0, cell)
        sheet.row += 2

    # -- tables --------------------------------------------------------
    def _add_table(self, tbl, sheet):
        grid_rows = self._table_grid_rows(tbl)
        if not grid_rows:
            return
        n_head = self._header_row_count(grid_rows)
        placed, merges, width = self._place_cells(grid_rows)
        if not width:
            return
        names = self._header_names(placed, width, n_head)
        offset = self._table_offset(sheet, width, n_head)

        base = sheet.row
        info = TableInfo()
        info.offset, info.width, info.first_row = offset, width, base
        info.names = names
        info.last_row = base + len(grid_rows) - 1
        info.n_data = len(grid_rows) - n_head
        if n_head:
            info.header_row = base + n_head - 1

        col_cells = self._put_table_cells(sheet, grid_rows, placed, names, n_head, base, offset)
        for r1, c1, r2, c2 in merges:
            sheet.merges.append((base + r1, offset + c1, base + r2, offset + c2))

        self._postprocess_columns(col_cells)
        sheet.tables.append(info)
        sheet.row = info.last_row + 2

    @staticmethod
    def _table_rows(tbl):
        """(<tr>, section) of the visible rows of a table, in document order."""
        rows = []
        for ch in tbl:
            tag = _tag(ch)
            if tag in ('thead', 'tbody', 'tfoot'):
                if is_hidden(ch):
                    continue
                rows.extend((tr, tag) for tr in ch if _tag(tr) == 'tr' and not is_hidden(tr))
            elif tag == 'tr' and not is_hidden(ch):
                rows.append((ch, 'tbody'))
        return rows

    def _table_grid_rows(self, tbl):
        """(<tr>, section, visible cells) of every row that has at least one visible cell."""
        grid_rows = []
        for tr, section in self._table_rows(tbl):
            cells = [c for c in tr if _tag(c) in ('td', 'th') and not is_hidden(c)]
            if cells:
                grid_rows.append((tr, section, cells))
        return grid_rows

    @staticmethod
    def _header_row_count(grid_rows):
        n_head = sum(1 for _tr, s, _c in grid_rows if s == 'thead')
        if not n_head and len(grid_rows) > 1 and all(_tag(c) == 'th' for c in grid_rows[0][2]):
            n_head = 1
        return n_head

    def _place_cells(self, grid_rows):
        """Place cells on a grid (handles colspan / rowspan): ``(placed, merges, width)``."""
        occupied = set()
        placed = []   # (r, c, el, rowspan, colspan)
        merges = []
        width = 0
        for r, (_tr, _section, cells) in enumerate(grid_rows):
            col = 0
            for el in cells:
                while (r, col) in occupied:
                    col += 1
                cs = self._span(el, 'colspan')
                rs = min(self._span(el, 'rowspan'), len(grid_rows) - r)
                for dr in range(rs):
                    for dc in range(cs):
                        occupied.add((r + dr, col + dc))
                if cs > 1 or rs > 1:
                    merges.append((r, col, r + rs - 1, col + cs - 1))
                placed.append((r, col, el, rs, cs))
                width = max(width, col + cs)
                col += cs
        return placed, merges, width

    @staticmethod
    def _header_names(placed, width, n_head):
        names = [''] * width
        for r, c, el, _rs, _cs in placed:
            if r < n_head:
                text = get_text(el).replace('\n', ' ').strip().lower()
                if text:
                    names[c] = text
        return names

    def _table_offset(self, sheet, width, n_head):
        """Column offset for 2-column totals tables under a previous table."""
        prev = sheet.tables[-1] if sheet.tables else None
        if prev and width == 2 and not n_head and prev.has_header and prev.width >= 3 \
                and sheet.row - 1 <= prev.last_row + 2 and self._last_col_numeric(sheet, prev):
            return prev.offset + prev.width - 2
        return 0

    def _put_table_cells(self, sheet, grid_rows, placed, names, n_head, base, offset):
        """Classify and store the cells of a table; returns the data cells by column."""
        col_cells = {}
        for r, c, el, _rs, _cs in placed:
            tr, section, _cells = grid_rows[r]
            is_header = r < n_head
            cell = classify_cell(el, names[c] if not is_header else '', self.opts)
            if is_header:
                self._style_header_cell(cell)
            else:
                if section == 'tfoot' or element_is_bold(tr):
                    cell.bold = True
                col_cells.setdefault(c, []).append(cell)
            sheet.put(base + r, offset + c, cell)
        return col_cells

    @staticmethod
    def _style_header_cell(cell):
        cell.kind, cell.fmt = 'text', None
        cell.value = cell.orig or None
        cell.bold = True
        cell.align = cell.align or 'center'
        cell.wrap = True

    @staticmethod
    def _span(el, attr):
        try:
            n = int(el.get(attr) or 1)
        except ValueError:
            n = 1
        if attr == 'colspan' and n > MAX_COLSPAN:
            return 1
        return max(n, 1)

    @staticmethod
    def _last_col_numeric(sheet, prev):
        c = prev.offset + prev.width - 1
        for r in range(prev.first_row, prev.last_row + 1):
            cell = sheet.cells.get((r, c))
            if cell and cell.kind == 'number':
                return True
        return False

    def _postprocess_columns(self, col_cells):
        ts = self.opts.thousands_sep
        for _c, cells in col_cells.items():
            kinds = {c.kind for c in cells if not c.empty}
            # Mixed percentage / text columns: keep what was printed.
            if 'percent' in kinds and ('text' in kinds):
                for cell in cells:
                    if cell.kind == 'percent':
                        cell.kind, cell.value, cell.fmt = 'text', cell.orig, None
            # Whole numbers >= 1000 without a thousands separator are most likely codes.
            if ts:
                for cell in cells:
                    if cell.kind == 'number' and cell.decimals == 0 and not cell.grouped \
                            and abs(cell.value) >= 1000 and cell.fmt == number_format(0, False):
                        cell.kind, cell.value, cell.fmt = 'text', cell.orig, None
            # Indentation relative to the shallowest cell of the column.
            indents = [c.indent for c in cells if not c.empty]
            if indents:
                low = min(indents)
                for cell in cells:
                    cell.indent = max(0, cell.indent - low)

    # -- finalisation --------------------------------------------------
    def _finalise(self, sheet):
        main = sheet.main_table
        if main:
            if main.header_row < FREEZE_LIMIT:
                sheet.freeze_row = main.header_row + 1
            sheet.filter = (main.header_row, main.offset, main.last_row, main.offset + main.width - 1)

    @staticmethod
    def _column_keys(table):
        """(name, occurrence) of each column, so that repeated header names stay distinct."""
        seen, keys = {}, []
        for name in table.names:
            n = seen.get(name, 0) + 1
            seen[name] = n
            keys.append((name, n))
        return keys

    def _all_lines(self, sheets):
        if len(sheets) < 2:
            return None
        mains = [s.main_table for s in sheets]
        if any(m is None for m in mains):
            return None
        firsts = {m.names[0] for m in mains if m.names}
        if len(firsts) != 1 or not next(iter(firsts)):
            return None

        order, display = self._merged_columns(mains)
        combined = Sheet('All lines')
        for i, c in enumerate(self._all_lines_header(sheets, mains, order, display)):
            combined.put(0, i, c)
        r_out = self._all_lines_rows(combined, sheets, mains, order)
        if r_out == 1:
            return None
        combined.row = r_out
        info = TableInfo()
        info.header_row, info.first_row, info.last_row = 0, 0, r_out - 1
        info.width, info.n_data = len(order) + 1, r_out - 1
        combined.tables.append(info)
        combined.freeze_row = 1
        combined.filter = (0, 0, r_out - 1, len(order))
        return combined

    def _merged_columns(self, mains):
        """Union of the columns of all main tables, keeping their relative order."""
        order = []
        display = {}
        for m in mains:
            prev = None
            for key, raw in zip(self._column_keys(m), m.names, strict=True):
                if key not in order:
                    if prev is None:
                        order.insert(0, key)
                    else:
                        order.insert(order.index(prev) + 1, key)
                display.setdefault(key, raw)
                prev = key
        return order, display

    def _all_lines_header(self, sheets, mains, order, display):
        cells = [Cell(value='Document', kind='text', bold=True, align='center')]
        for key in order:
            title = self._original_title(sheets, mains, key) or display[key]
            cells.append(Cell(value=title, kind='text', bold=True, align='center', wrap=True))
        return cells

    def _original_title(self, sheets, mains, key):
        """Original capitalisation of a header, taken from the first sheet that has the column."""
        for s, m in zip(sheets, mains, strict=True):
            keys = self._column_keys(m)
            if key in keys:
                cell = s.cells.get((m.header_row, m.offset + keys.index(key)))
                if cell and cell.value:
                    return cell.value
        return None

    @staticmethod
    def _data_row(sheet, table, r):
        """Cells of a data row, or None for empty rows, section headings and subtotals."""
        row_cells = [sheet.cells.get((r, table.offset + c)) for c in range(table.width)]
        non_empty = [c for c in row_cells if c is not None and not c.empty]
        if not non_empty or all(c.bold for c in non_empty):
            return None
        return row_cells

    def _all_lines_rows(self, combined, sheets, mains, order):
        """Copy the data rows of every main table into ``combined``; returns the next free row."""
        r_out = 1
        for s, m in zip(sheets, mains, strict=True):
            idx = {key: i for i, key in enumerate(self._column_keys(m))}
            for r in range(m.header_row + 1, m.last_row + 1):
                row_cells = self._data_row(s, m, r)
                if row_cells is None:
                    continue
                combined.put(r_out, 0, Cell(value=s.title, kind='text'))
                self._copy_row(combined, r_out, row_cells, idx, order)
                r_out += 1
        return r_out

    @staticmethod
    def _copy_row(combined, r_out, row_cells, idx, order):
        for j, key in enumerate(order, 1):
            src = idx.get(key)
            if src is None:
                continue
            cell = row_cells[src]
            if cell is not None and not cell.empty:
                new = copy.copy(cell)
                new.bold = False
                combined.put(r_out, j, new)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def _cell_width(cell):
    if cell.empty or cell.nowidth:
        return 0
    if cell.kind in ('number', 'percent'):
        digits = len('%.*f' % (cell.decimals, abs(cell.value))) if cell.kind == 'number' else 6
        return digits + 6
    if cell.kind in ('date', 'datetime'):
        return 11 if cell.kind == 'date' else 17
    longest = max(len(line) for line in str(cell.value).split('\n'))
    return longest + cell.indent * 2


def _format_factory(wb):
    """Return ``fmt_for(cell)``: the workbook format of a cell, created once per distinct style."""
    formats = {}

    def fmt_for(cell):
        key = (cell.bold, cell.align, cell.fmt, cell.indent, cell.wrap, cell.size)
        if key not in formats:
            props = {'valign': 'top'}
            if cell.bold:
                props['bold'] = True
            if cell.align:
                props['align'] = cell.align
            if cell.fmt:
                props['num_format'] = cell.fmt
            if cell.indent:
                props['indent'] = cell.indent
            if cell.wrap:
                props['text_wrap'] = True
            if cell.size:
                props['font_size'] = cell.size
            formats[key] = wb.add_format(props)
        return formats[key]

    return fmt_for


def _merged_positions(sheet):
    """(all cells covered by merged ranges, merged range by its top-left cell)."""
    merged = set()
    for r1, c1, r2, c2 in sheet.merges:
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                merged.add((r, c))
    merge_origin = {(r1, c1): (r1, c1, r2, c2) for r1, c1, r2, c2 in sheet.merges}
    return merged, merge_origin


def _write_value(ws, r, c, cell, fmt):
    if cell.kind in ('number', 'percent'):
        ws.write_number(r, c, cell.value, fmt)
    elif cell.kind in ('date', 'datetime'):
        ws.write_datetime(r, c, cell.value, fmt)
    else:
        ws.write_string(r, c, str(cell.value), fmt)


def _write_cells(ws, sheet, fmt_for):
    """Write all cells of a sheet; returns the content width needed by each column."""
    merged, merge_origin = _merged_positions(sheet)
    widths = {}
    for (r, c), cell in sorted(sheet.cells.items()):
        if (r, c) in merged and (r, c) not in merge_origin:
            continue
        fmt = fmt_for(cell)
        if (r, c) in merge_origin:
            _r1, _c1, r2, c2 = merge_origin[(r, c)]
            ws.merge_range(r, c, r2, c2, '', fmt)
        if cell.empty:
            if (r, c) not in merge_origin:
                ws.write_blank(r, c, None, fmt)
            continue
        _write_value(ws, r, c, cell, fmt)
        if (r, c) not in merged:
            widths[c] = max(widths.get(c, 0), _cell_width(cell))
    return widths


def _write_sheet(wb, sheet, fmt_for):
    ws = wb.add_worksheet(sheet.name)
    widths = _write_cells(ws, sheet, fmt_for)
    max_col = max((c for _r, c in sheet.cells), default=0)
    for c in range(max_col + 1):
        w = widths.get(c, 0)
        ws.set_column(c, c, min(max(w, DEFAULT_WIDTH), MAX_WIDTH))
    if sheet.freeze_row:
        ws.freeze_panes(sheet.freeze_row, 0)
    if sheet.filter:
        ws.autofilter(*sheet.filter)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)


def write_workbook(sheets, title):
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {'in_memory': True, 'default_date_format': 'yyyy-mm-dd',
                                   'strings_to_numbers': False, 'strings_to_formulas': False,
                                   'strings_to_urls': False})
    wb.set_properties({'title': title or 'Report', 'comments': 'Generated by Odoo2XL - Odoo Excel Reports'})
    fmt_for = _format_factory(wb)
    for sheet in sheets:
        _write_sheet(wb, sheet, fmt_for)
    wb.close()
    return buf.getvalue()


def convert_report_html(html_source, options=None):
    """Convert the HTML of an Odoo report to the content of an .xlsx file (bytes)."""
    opts = options or ConverterOptions()
    sheets = Converter(opts).convert(html_source)
    title = sheets[0].title if len(sheets) == 1 else opts.title
    return write_workbook(sheets, title)
