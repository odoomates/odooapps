import io
from datetime import date
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.om_account_bill_ocr.tests import bills

TEXT_EXTRACT = 'odoo.addons.om_account_bill_ocr.tools.text_extract'


def pdf_of(text, scanned=False):
    """ A PDF of the text, the columns in place as a bill prints them; a scan has no text layer. """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    if scanned:
        pdf.rect(40, 400, 400, 300, fill=1)
    else:
        pdf.setFont('Courier', 8)
        y = 800
        for line in text.split('\n'):
            pdf.drawString(30, y, line)
            y -= 11
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@tagged('post_install', '-at_install')
class TestBillOcr(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.om_bill_ocr_mode = 'auto'
        cls.journal = cls.company_data['default_journal_purchase']
        cls.env.ref('base.EUR').active = True
        cls.tax_19 = cls.env['account.tax'].create({
            'name': 'Vorsteuer 19%', 'amount': 19.0, 'amount_type': 'percent', 'type_tax_use': 'purchase',
            'company_id': cls.company.id,
        })
        cls.mueller = cls.env['res.partner'].create({
            'name': 'Bürobedarf Müller GmbH', 'vat': 'DE123456789', 'is_company': True,
            'company_id': False,
        })
        cls.expense = cls.company_data['default_account_expense']

    def _upload(self, text, name='bill.pdf', scanned=False, mimetype='application/pdf', raw=None):
        attachment = self.env['ir.attachment'].create({
            'name': name, 'raw': raw or pdf_of(text, scanned), 'mimetype': mimetype,
        })
        return self.journal.with_context(default_move_type='in_invoice')._create_document_from_attachment(
            attachment.ids)

    def test_a_bill_is_read_on_upload(self):
        bill = self._upload(bills.EU)
        self.assertEqual(bill.partner_id, self.mueller)
        self.assertEqual(bill.ref, 'RE-58213')
        self.assertEqual(bill.invoice_date, date(2026, 2, 5))
        self.assertEqual(bill.currency_id.name, 'EUR')
        self.assertEqual(bill.invoice_line_ids.mapped('name'),
                         ['Ordner breit, blau', 'Kopierpapier 500 Blatt', 'Druckerservice (Stunden)'])
        self.assertEqual(bill.invoice_line_ids.mapped('quantity'), [20.0, 100.0, 3.0])
        # the tax of the rate printed on the bill, and the totals of the bill
        self.assertEqual(bill.invoice_line_ids.tax_ids, self.tax_19)
        self.assertAlmostEqual(bill.amount_untaxed, 708.0)
        self.assertAlmostEqual(bill.amount_total, 842.52)
        self.assertEqual(bill.om_ocr_data['found_by'], 'vat')
        self.assertEqual(bill.om_ocr_data['source'], 'text')
        self.assertIn('Account', bill.om_ocr_to_check or '')

    def test_the_vendor_by_its_bank_account(self):
        vendor = self.env['res.partner'].create({'name': 'Somebody Else'})
        self.env['res.partner.bank'].create({'partner_id': vendor.id, 'account_number': 'DE89 3704 0044 0532 0130 00'})
        bill = self._upload(bills.EU.replace('USt-IdNr.: DE 123 456 789', ''))
        self.assertEqual(bill.partner_id, vendor)
        self.assertEqual(bill.om_ocr_data['found_by'], 'iban')

    def test_the_own_tax_number_is_not_the_vendor(self):
        # the bill printing the tax number of the company receiving it, and no other
        self.company.vat = 'DE123456789'
        self.mueller.write({'vat': False, 'name': 'Office Supplies Berlin'})
        bill = self._upload(bills.EU)
        self.assertFalse(bill.partner_id)
        self.assertIn('Vendor', bill.om_ocr_to_check)
        self.assertEqual(bill.om_ocr_state, 'to_check')

    def test_a_bill_read_on_one_line_when_its_lines_do_not_add_up(self):
        bill = self._upload(bills.EU.replace('410,00', '401,00'))
        self.assertEqual(len(bill.invoice_line_ids), 1)
        self.assertAlmostEqual(bill.invoice_line_ids.price_unit, 708.0)
        self.assertAlmostEqual(bill.amount_total, 842.52)
        self.assertEqual(bill.om_ocr_data['line_mode'], 'single')

    def test_posting_teaches_the_vendor(self):
        bill = self._upload(bills.EU)
        bill.invoice_line_ids.account_id = self.expense
        bill.action_post()
        profile = self.env['om.bill.ocr.profile'].search([('partner_id', '=', self.mueller.id)])
        self.assertEqual(profile.account_id, self.expense)
        self.assertEqual(profile.tax_ids, self.tax_19)
        self.assertEqual(profile.anchor_ref, 'Rechnungsnummer')
        self.assertEqual(profile.anchor_invoice_date, 'Rechnungsdatum')
        self.assertEqual(profile.anchor_amount_total, 'Gesamtbetrag')
        self.assertEqual(profile.bill_count, 1)

        # the next bill is booked as the first one was
        second = self._upload(bills.REPEAT)
        self.assertEqual(second.partner_id, self.mueller)
        self.assertEqual(second.invoice_line_ids.account_id, self.expense)
        self.assertEqual(second.ref, 'RE-58377')
        self.assertEqual(second.om_ocr_state, 'done', second.om_ocr_to_check)

    def test_a_vendor_without_identifier_is_learned(self):
        caterer = self.env['res.partner'].create({'name': 'Lakeside Catering', 'company_id': False})
        bill = self._upload(bills.NO_IDENTIFIER)
        # found by its name, its fields not labeled the usual way
        self.assertEqual(bill.partner_id, caterer)
        self.assertEqual(bill.om_ocr_data['found_by'], 'name')
        self.assertFalse(bill.ref)
        # its total: the largest amount, to be checked
        self.assertAlmostEqual(bill.amount_total, 1800.0)
        self.assertIn('Total', bill.om_ocr_to_check)
        # the accountant fills them in, and posts
        bill.write({'ref': 'LC-2026-118', 'invoice_date': date(2026, 3, 4)})
        bill.invoice_line_ids.account_id = self.expense
        bill.action_post()
        profile = self.env['om.bill.ocr.profile'].search([('partner_id', '=', caterer.id)])
        self.assertEqual(profile.anchor_ref, 'Reference')
        self.assertEqual(profile.anchor_amount_total, 'Sum to pay')
        self.assertIn('Lakeside Catering', profile._match_keys())

        # its next bill: renamed in the database, the letterhead still tells it
        caterer.name = 'Lakeside Catering Ltd (Events)'
        second = self._upload(bills.NO_IDENTIFIER_NEXT)
        self.assertEqual(second.partner_id, caterer)
        self.assertEqual(second.om_ocr_data['found_by'], 'learned')
        self.assertEqual(second.ref, 'LC-2026-131')
        self.assertAlmostEqual(second.amount_total, 540.0)

    def test_the_date_order_of_a_vendor_is_learned(self):
        self.env['res.lang']._activate_lang('en_US')
        caterer = self.env['res.partner'].create({'name': 'Lakeside Catering', 'company_id': False})
        bill = self._upload(bills.NO_IDENTIFIER)
        # en_US reads 04/03/2026 as April 3, and says the date is to be checked
        self.assertEqual(bill.invoice_date, date(2026, 4, 3))
        self.assertIn('Bill Date', bill.om_ocr_to_check)
        bill.write({'invoice_date': date(2026, 3, 4), 'ref': 'LC-2026-118'})
        bill.invoice_line_ids.account_id = self.expense
        bill.action_post()
        self.assertEqual(self.env['om.bill.ocr.profile'].search([('partner_id', '=', caterer.id)]).date_order, 'dmy')
        second = self._upload(bills.NO_IDENTIFIER_NEXT)
        self.assertEqual(second.invoice_date, date(2026, 3, 5))

    def test_a_scan_without_tesseract(self):
        with patch(f'{TEXT_EXTRACT}.tesseract_available', return_value=False):
            bill = self._upload(bills.EU, scanned=True)
        self.assertFalse(bill.invoice_line_ids)
        self.assertFalse(bill.om_ocr_state)
        self.assertTrue(any('tesseract-ocr' in message.body for message in bill.message_ids))

    def test_a_scan_read_by_tesseract(self):
        with patch(f'{TEXT_EXTRACT}.tesseract_available', return_value=True), \
                patch(f'{TEXT_EXTRACT}._ocr_pdf', return_value=bills.EU) as ocr:
            bill = self._upload(bills.EU, scanned=True)
        ocr.assert_called_once()
        self.assertEqual(bill.partner_id, self.mueller)
        self.assertAlmostEqual(bill.amount_total, 842.52)
        self.assertEqual(bill.om_ocr_data['source'], 'ocr')

    def test_a_photo_read_by_tesseract(self):
        with patch(f'{TEXT_EXTRACT}.tesseract_available', return_value=True), \
                patch(f'{TEXT_EXTRACT}._ocr_raw_image', return_value=bills.AE) as ocr:
            bill = self._upload(None, name='bill.jpg', mimetype='image/jpeg', raw=b'\xff\xd8\xff\xe0 not really a jpeg')
        ocr.assert_called_once()
        self.assertEqual(bill.ref, 'GS-7781')
        self.assertEqual(bill.om_ocr_data['source'], 'ocr')

    def test_reading_on_demand(self):
        self.company.om_bill_ocr_mode = 'manual'
        bill = self._upload(bills.EU)
        self.assertFalse(bill.invoice_line_ids)
        self.assertTrue(bill.om_ocr_can_read)
        bill.action_om_ocr_read()
        self.assertEqual(bill.partner_id, self.mueller)
        self.assertEqual(len(bill.invoice_line_ids), 3)
        self.assertFalse(bill.om_ocr_can_read)
        with self.assertRaisesRegex(UserError, 'already has lines'):
            bill.action_om_ocr_read()

    def test_the_name_of_the_receiving_company_is_not_the_vendor(self):
        """ The bill names its customer, the company receiving it: a partner of that name is no vendor. """
        self.company.name = 'Harbour Trading LLC'
        self.env['res.partner'].create({'name': 'Harbour Trading LLC', 'company_id': False})
        bill = self._upload(bills.ODOO_LAYOUT)
        self.assertFalse(bill.partner_id)
        # the table of the Odoo layout: a description wrapped around its numbers, a quantity glued to it
        self.assertEqual(bill.invoice_line_ids.mapped('name'),
                         ['Laser printer toner, black', 'Archive boxes (pack of 10)', 'On-site printer maintenance'])
        self.assertEqual(bill.invoice_line_ids.mapped('quantity'), [6.0, 3.0, 2.0])
        self.assertAlmostEqual(bill.amount_untaxed, 681.7)

    def test_switched_off(self):
        self.company.om_bill_ocr_mode = 'off'
        bill = self._upload(bills.EU)
        self.assertFalse(bill.invoice_line_ids)
        self.assertFalse(bill.om_ocr_can_read)

    def test_customer_invoices_are_not_read(self):
        attachment = self.env['ir.attachment'].create({'name': 'bill.pdf', 'raw': pdf_of(bills.EU),
                                                       'mimetype': 'application/pdf'})
        invoice = self.company_data['default_journal_sale'].with_context(
            default_move_type='out_invoice')._create_document_from_attachment(attachment.ids)
        self.assertFalse(invoice.invoice_line_ids)
        self.assertFalse(invoice.om_ocr_state)

    def test_the_last_bill_of_the_vendor_gives_the_account(self):
        other_expense = self.expense.copy({'code': '600999'})
        last = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.mueller.id, 'invoice_date': '2026-01-15',
            'invoice_line_ids': [Command.create({'name': 'x', 'price_unit': 10.0, 'account_id': other_expense.id,
                                                'tax_ids': [Command.set(self.tax_19.ids)]})],
        })
        last.action_post()
        bill = self._upload(bills.EU)
        self.assertEqual(bill.invoice_line_ids.account_id, other_expense)
        self.assertNotIn('Account', bill.om_ocr_to_check or '')

    def test_the_settings(self):
        settings = self.env['res.config.settings'].create({})
        settings.om_bill_ocr_mode = 'manual'
        settings.om_bill_ocr_languages = 'eng+deu'
        settings.execute()
        self.assertEqual(self.env.company.om_bill_ocr_mode, 'manual')
        self.assertEqual(self.env.company.om_bill_ocr_languages, 'eng+deu')
