from datetime import date

from odoo.tests import BaseCase, tagged

from odoo.addons.om_account_bill_ocr.tools import bill_parser
from odoo.addons.om_account_bill_ocr.tests import bills


@tagged('post_install', '-at_install')
class TestBillParser(BaseCase):
    """ The text of the bills of several countries read into their fields, without a database. """

    def test_amounts_whatever_their_separators(self):
        for printed, value in (('1,234.56', 1234.56), ('1.234,56', 1234.56), ('1 234,56', 1234.56),
                               ("1'234.56", 1234.56), ('1234', 1234.0), ('(12.50)', -12.5), ('1,234', 1234.0),
                               ('17,000.00', 17000.0), ('0,95', 0.95)):
            with self.subTest(printed=printed):
                self.assertEqual(bill_parser.parse_amount(printed), value)
        # a currency of 3 decimals
        self.assertEqual(bill_parser.parse_amount('1.250', decimals=3), 1.25)

    def test_dates_whatever_their_format(self):
        for printed, value in (('2026-03-12', date(2026, 3, 12)), ('12 March 2026', date(2026, 3, 12)),
                               ('March 12, 2026', date(2026, 3, 12)), ('12-Mar-2026', date(2026, 3, 12)),
                               ('12.03.2026', date(2026, 3, 12)), ('5. Februar 2026', date(2026, 2, 5)),
                               ('25/12/26', date(2026, 12, 25))):
            with self.subTest(printed=printed):
                self.assertEqual(bill_parser.find_dates(printed)[0][0], value)
        # a date read both ways follows the order given
        self.assertEqual(bill_parser.find_dates('04/03/2026', 'dmy')[0][0], date(2026, 3, 4))
        self.assertEqual(bill_parser.find_dates('04/03/2026', 'mdy')[0][0], date(2026, 4, 3))
        # a dotted date is day first, whatever the order given
        self.assertEqual(bill_parser.find_dates('05.02.2026', 'mdy')[0][0], date(2026, 2, 5))

    def test_a_us_bill(self):
        bill = bill_parser.parse_bill(bills.US, date_order='mdy', known_currencies={'USD', 'EUR'})
        self.assertEqual(bill['ref'], 'INV-2026-0042')
        self.assertEqual(bill['invoice_date'], date(2026, 3, 12))
        self.assertEqual(bill['invoice_date_due'], date(2026, 4, 11))
        self.assertEqual((bill['amount_untaxed'], bill['amount_tax'], bill['amount_total']), (439.98, 37.4, 477.38))
        self.assertTrue(bill['totals_consistent'])
        self.assertEqual(bill['currency'], 'USD')
        self.assertEqual(bill['po'], 'PO00017')
        self.assertEqual(bill['emails'], ['billing@acmeoffice.com'])
        self.assertEqual([(line['quantity'], line['price_unit'], line['amount']) for line in bill['lines']],
                         [(10, 24.5, 245.0), (4, 38.75, 155.0), (2, 19.99, 39.98)])
        # a description on two lines, and the numbers inside a description kept in it
        self.assertEqual(bill['lines'][2]['name'], 'Desk organizer, bamboo with drawer')
        self.assertEqual(bill['lines'][0]['name'], 'Copy paper A4 80 g, box of 5')

    def test_a_german_bill(self):
        bill = bill_parser.parse_bill(bills.EU, date_order='dmy', known_currencies={'EUR'})
        self.assertEqual(bill['ref'], 'RE-58213')
        self.assertEqual(bill['invoice_date'], date(2026, 2, 5))
        self.assertEqual(bill['invoice_date_due'], date(2026, 3, 7))
        self.assertEqual((bill['amount_untaxed'], bill['amount_tax'], bill['amount_total']), (708.0, 134.52, 842.52))
        self.assertEqual(bill['vat_numbers'], ['DE123456789'])
        self.assertEqual(bill['ibans'], ['DE89370400440532013000'])
        self.assertEqual(len(bill['lines']), 3)

    def test_an_indian_bill_with_two_taxes(self):
        bill = bill_parser.parse_bill(bills.IN, date_order='dmy')
        self.assertEqual(bill['ref'], 'ST/25-26/0193')
        self.assertEqual(bill['invoice_date'], date(2025, 8, 14))
        # CGST and SGST of the same amount: both are taxes
        self.assertEqual((bill['amount_untaxed'], bill['amount_tax'], bill['amount_total']), (29000.0, 5220.0, 34220.0))
        self.assertTrue(bill['totals_consistent'])
        self.assertEqual(bill['vat_numbers'], ['27AAPFU0939F1ZV'])
        # the HSN code column is no quantity
        self.assertEqual([(line['quantity'], line['price_unit']) for line in bill['lines']], [(2, 8500.0), (5, 2400.0)])

    def test_a_uae_bill_ends_its_lines_at_the_vat(self):
        bill = bill_parser.parse_bill(bills.AE, date_order='dmy', known_currencies={'AED', 'USD'})
        self.assertEqual(bill['ref'], 'GS-7781')
        self.assertEqual(bill['vat_numbers'], ['100234567800003'])
        self.assertEqual(bill['currency'], 'AED')
        self.assertEqual([line['amount'] for line in bill['lines']], [1200.0])
        self.assertEqual((bill['amount_untaxed'], bill['amount_tax'], bill['amount_total']), (1200.0, 60.0, 1260.0))

    def test_a_bill_without_a_table(self):
        bill = bill_parser.parse_bill(bills.SIMPLE, date_order='dmy', known_currencies={'USD'})
        self.assertEqual(bill['ref'], '1187')
        self.assertEqual(bill['invoice_date'], date(2026, 1, 20))
        self.assertEqual(bill['amount_total'], 350.0)
        self.assertEqual(bill['currency'], 'USD')
        self.assertFalse(bill['lines'])
        self.assertFalse(bill['totals_consistent'])

    def test_lines_kept_only_when_they_add_up(self):
        broken = bills.US.replace('245.00', '254.00')
        bill = bill_parser.parse_bill(broken, date_order='mdy')
        self.assertFalse(bill['lines'])
        self.assertEqual(bill['amount_total'], 477.38)

    def test_the_labels_a_vendor_prints(self):
        anchors = {'ref': 'Reference', 'invoice_date': 'Dated', 'amount_total': 'Sum to pay'}
        bill = bill_parser.parse_bill(bills.NO_IDENTIFIER, date_order='dmy', anchors=anchors)
        self.assertEqual(bill['ref'], 'LC-2026-118')
        self.assertEqual(bill['invoice_date'], date(2026, 3, 4))
        self.assertEqual(bill['amount_total'], 1800.0)
        # where they are learned from
        text = bills.NO_IDENTIFIER
        self.assertEqual(bill_parser.label_before(text, ['LC-2026-118']), 'Reference')
        self.assertEqual(bill_parser.label_at(text, bill_parser.amount_positions(text, 1800.0)[-1]), 'Sum to pay')
        self.assertEqual(bill_parser.label_at(bills.US, bill_parser.amount_positions(bills.US, 477.38)[-1]),
                         'Amount Due')

    def test_the_table_of_an_odoo_invoice(self):
        bill = bill_parser.parse_bill(bills.ODOO_LAYOUT, date_order='mdy')
        self.assertEqual(bill['ref'], 'INV/2026/00001')
        self.assertEqual(bill['invoice_date'], date(2026, 9, 14))
        self.assertEqual((bill['amount_untaxed'], bill['amount_tax'], bill['amount_total']), (681.7, 102.26, 783.96))
        self.assertEqual([(line['name'], line['quantity'], line['price_unit']) for line in bill['lines']], [
            ('Laser printer toner, black', 6.0, 72.5),
            ('Archive boxes (pack of 10)', 3.0, 18.9),
            ('On-site printer maintenance', 2.0, 95.0),
        ])
