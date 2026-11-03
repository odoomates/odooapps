"""Tests of the HTML -> xlsx converter."""
import datetime
import io
import os

from odoo.tests import BaseCase

from ..lib import html_to_xlsx as h

HERE = os.path.dirname(__file__)


def convert(html, **kw):
    import openpyxl
    data = h.convert_report_html(html, h.ConverterOptions(**kw))
    return openpyxl.load_workbook(io.BytesIO(data))


class TestParsing(BaseCase):
    def test_numbers(self):
        self.assertEqual(h.parse_number('1,234.50', '.', ','), (1234.5, 2, True))
        self.assertEqual(h.parse_number('(12.00)', '.', ','), (-12.0, 2, False))
        self.assertEqual(h.parse_number('12.00-', '.', ','), (-12.0, 2, False))
        self.assertEqual(h.parse_number('−12', '.', ','), (-12.0, 0, False))
        self.assertEqual(h.parse_number('1.234,50', ',', '.'), (1234.5, 2, True))
        self.assertEqual(h.parse_number('1 234,50', ',', ' '), (1234.5, 2, True))
        self.assertIsNone(h.parse_number('00123', '.', ','))
        self.assertIsNone(h.parse_number('12abc', '.', ','))
        self.assertIsNone(h.parse_number('1,23', '.', ','))

    def test_dates(self):
        self.assertEqual(h.parse_date('10/12/2026', '%m/%d/%Y'), ('date', datetime.date(2026, 10, 12)))
        self.assertEqual(h.parse_date('12/10/2026', '%d/%m/%Y'), ('date', datetime.date(2026, 10, 12)))
        self.assertEqual(h.parse_date('2026-10-12', '%m/%d/%Y'), ('date', datetime.date(2026, 10, 12)))
        self.assertEqual(h.parse_date('10/12/2026 03:30 PM', '%m/%d/%Y'),
                         ('datetime', datetime.datetime(2026, 10, 12, 15, 30)))
        self.assertIsNone(h.parse_date('13/45/2026', '%m/%d/%Y'))


class TestInvoice(BaseCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, 'sample_invoice.html'), 'rb') as f:
            cls.wb = convert(f.read(), title='Invoices')

    def test_sheets(self):
        self.assertEqual(self.wb.sheetnames[0], 'All lines')
        self.assertIn('Invoice INV 2026 0001', self.wb.sheetnames)
        self.assertEqual(len(self.wb.sheetnames), 3)

    def test_header_footer_dropped(self):
        for ws in self.wb:
            for row in ws.iter_rows(values_only=True):
                for v in row:
                    self.assertNotIn('Dropped', str(v))
                    self.assertNotIn('hidden', str(v))

    def test_typed_values(self):
        ws = self.wb['Invoice INV 2026 0001']
        cells = {c.coordinate: c for row in ws.iter_rows() for c in row if c.value is not None}
        values = [c.value for c in cells.values()]
        self.assertIn(11404.75, values)
        self.assertIn(1200.5, values)
        self.assertIn(10.0, values)           # quantity with unit
        self.assertIn(0.05, values)           # percentage
        self.assertIn(-10.0, values)
        self.assertIn(datetime.datetime(2026, 10, 12), values)
        self.assertIn('00123', values)        # code kept as text
        self.assertIn('Untaxed Amount', values)

    def test_freeze_and_filter(self):
        ws = self.wb['Invoice INV 2026 0001']
        self.assertTrue(ws.freeze_panes)
        self.assertTrue(ws.auto_filter.ref)

    def test_totals_aligned_under_amount(self):
        ws = self.wb['Invoice INV 2026 0001']
        for row in ws.iter_rows():
            for c in row:
                if c.value == 'Untaxed Amount':
                    self.assertEqual(c.column, 4)       # column D (offset = width - 2)
                    self.assertEqual(ws.cell(c.row, 5).value, 11592.75)

    def test_all_lines(self):
        ws = self.wb['All lines']
        rows = list(ws.iter_rows(values_only=True))
        self.assertEqual(rows[0][0], 'Document')
        docs = [r[0] for r in rows[1:]]
        self.assertEqual(docs.count('Invoice INV/2026/0001'.replace('/', ' ')) + 0, 0)
        self.assertEqual(len(rows) - 1, 4)  # 3 lines of doc 1 (section row skipped) + 1 of doc 2
