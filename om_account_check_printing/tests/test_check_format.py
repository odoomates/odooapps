import base64
import re
from datetime import date

from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

LAYOUT = 'om_account_check_printing.action_report_check'


@tagged('post_install', '-at_install')
class TestCheckFormat(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = cls.company_data['default_journal_bank']
        cls.bank.check_manual_sequencing = True
        cls.env.company.account_check_printing_layout = LAYOUT
        cls.check_method = cls.bank.outbound_payment_method_line_ids.filtered(
            lambda line: line.code == 'check_printing')
        cls.a4_format = cls.env.ref('om_account_check_printing.check_format_a4_top')
        cls.leaf_format = cls.env.ref('om_account_check_printing.check_format_leaf')

    def _pay_bill(self, amount=1234.5):
        bill = self.init_invoice('in_invoice', amounts=[amount], taxes=[], invoice_date='2026-03-01', post=True)
        payments = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=bill.ids).create({
            'journal_id': self.bank.id,
            'payment_method_line_id': self.check_method.id,
            'payment_date': date(2026, 3, 15),
        })._create_payments()
        return bill, payments

    def test_print_on_the_cheque_leaf(self):
        self.bank.check_format_id = self.leaf_format
        bill, payment = self._pay_bill()
        self.assertTrue(self.check_method)
        action = payment.print_checks()
        self.assertEqual(action['report_name'], 'om_account_check_printing.report_check')
        self.assertEqual(action['context']['om_check_format_id'], self.leaf_format.id)
        self.assertTrue(payment.is_sent)

        report = self.env.ref(LAYOUT).with_context(om_check_format_id=self.leaf_format.id)
        html = report._render_qweb_html(report.report_name, payment.ids)[0].decode()
        self.assertIn(payment.partner_id.name, html)
        self.assertIn('**1,234.50**', html)
        self.assertIn('15032026', html)
        self.assertIn('A/C PAYEE ONLY', html)
        words = self.leaf_format._format_words(1234.5, payment.currency_id)
        self.assertTrue(words.isupper() and words.endswith('ONLY'))
        self.assertIn(words, html)
        self.assertIn('width: 201.0mm; height: 91.0mm', html)

        paperformat = report.get_paperformat()
        self.assertEqual(paperformat, self.leaf_format.paperformat_id)
        self.assertEqual((paperformat.format, paperformat.page_width, paperformat.page_height), ('custom', 202, 92))
        self.assertEqual(paperformat.margin_top, 0)

    def test_stubs_list_the_bills_paid(self):
        self.bank.check_format_id = self.a4_format
        bill, payment = self._pay_bill()
        payment.print_checks()
        report = self.env.ref(LAYOUT).with_context(om_check_format_id=self.a4_format.id)
        html = report._render_qweb_html(report.report_name, payment.ids)[0].decode()
        self.assertEqual(payment.memo, bill.name)
        self.assertEqual(html.count(bill.name), 3)  # the memo on the cheque and the bill on both stubs
        self.assertEqual(
            self.env.ref(LAYOUT).with_context(om_check_format_id=self.a4_format.id).get_paperformat().format, 'A4')

    def test_format_changes_and_test_print(self):
        check_format = self.leaf_format.copy({'name': 'My Bank'})
        paperformat = check_format.paperformat_id
        self.assertNotEqual(paperformat, self.leaf_format.paperformat_id)
        check_format.write({'page_width': 180.0})
        self.assertEqual(paperformat.page_width, 180.0)
        with self.assertRaises(ValidationError):
            check_format.page_height = 0.0

        date_line = check_format.line_ids.filtered(lambda line: line.field == 'date')
        check_format.offset_x = 2.5
        self.assertIn('left: 154.50mm', date_line._get_style())
        self.assertIn('letter-spacing: 3.20mm', date_line._get_style())

        action = check_format.action_print_test()
        self.assertEqual(action['report_name'], 'om_account_check_printing.report_check_test')
        report = self.env.ref('om_account_check_printing.action_report_check_test')
        html = report.with_context(om_check_format_id=check_format.id)._render_qweb_html(
            report.report_name, check_format.ids)[0].decode()
        self.assertIn('Sample Supplier Ltd', html)

    def test_no_format(self):
        self.env['account.check.format'].search([]).action_archive()
        bill, payment = self._pay_bill()
        with self.assertRaises(RedirectWarning):
            payment.print_checks()

    def test_other_layouts_are_left_alone(self):
        self.bank.bank_check_printing_layout = False
        self.env.company.account_check_printing_layout = 'disabled'
        bill, payment = self._pay_bill()
        with self.assertRaises(RedirectWarning):
            # the standard message asking for a layout
            payment.print_checks()
        self.assertFalse(payment.is_sent)

    def test_every_installed_format_prints(self):
        """ The formats shipped with the module print their sample on a page of their own size. """
        report = self.env.ref('om_account_check_printing.action_report_check_test')
        formats = self.env['account.check.format'].search([('company_id', '=', False)])
        self.assertGreaterEqual(len(formats), 10)
        for check_format in formats:
            with self.subTest(check_format=check_format.name):
                html = report.with_context(om_check_format_id=check_format.id)._render_qweb_html(
                    report.report_name, check_format.ids)[0].decode()
                self.assertIn('Sample Supplier Ltd', html)
                width, height = check_format._get_page_size()
                self.assertIn('width: %.1fmm; height: %.1fmm' % (width - 1, height - 1), html)
                for line in check_format.line_ids:
                    self.assertLessEqual(line.x + line.width, width + 0.1, 'the field stays on the page')
                    self.assertLessEqual(line.y, height, 'the field stays on the page')

    def test_the_format_of_the_country_is_taken_by_default(self):
        self.bank.check_format_id = False
        self.env.company.country_id = self.env.ref('base.us')
        self.assertEqual(self.bank._get_check_format(),
                         self.env.ref('om_account_check_printing.check_format_us_top'))
        self.env.company.country_id = self.env.ref('base.ca')
        self.assertEqual(self.bank._get_check_format(),
                         self.env.ref('om_account_check_printing.check_format_us_ca_leaf'))
        self.env.company.country_id = self.env.ref('base.be')
        self.assertEqual(self.bank._get_check_format(), self.a4_format,
                         'without a format of its own, a country takes the first format used anywhere')
        self.bank.check_format_id = self.leaf_format
        self.assertEqual(self.bank._get_check_format(), self.leaf_format, 'the format of the journal comes first')

    def test_date_formats(self):
        check_format = self.leaf_format.copy({'name': 'Dates'})
        day = date(2026, 3, 5)
        for date_format, expected in (('%Y%m%d', '20260305'), ('%d.%m.%Y', '05.03.2026'),
                                      ('%Y/%m/%d', '2026/03/05'), ('%B %d, %Y', 'March 05, 2026')):
            check_format.date_format = date_format
            self.assertEqual(check_format._format_date(day), expected)

    def test_cents_as_a_fraction(self):
        check_format = self.env.ref('om_account_check_printing.check_format_us_ca_leaf')
        usd = self.env.ref('base.USD')
        words = check_format._format_words(1234.5, usd)
        self.assertTrue(words.endswith(' AND 50/100'), words)
        self.assertIn('THOUSAND', words)
        self.assertNotIn('CENTS', words)
        self.assertTrue(check_format._format_words(12.0, usd).endswith(' AND 00/100'))
        self.assertTrue(check_format._format_words(7.009, usd).endswith(' AND 01/100'), 'rounded to the cent')
        kwd = self.env.ref('base.KWD')
        kwd.active = True
        self.assertTrue(check_format._format_words(3.25, kwd).endswith(' AND 250/1000'))

    def test_words_in_a_second_language(self):
        self.env['res.lang']._activate_lang('fr_FR')
        check_format = self.leaf_format.copy({'name': 'Bilingual', 'words_lang_2': 'fr_FR'})
        check_format.line_ids.create({
            'format_id': check_format.id, 'field': 'amount_in_words_2', 'x': 30, 'y': 45, 'width': 125,
        })
        currency = self.env.company.currency_id
        values = check_format._get_field_values('Partner', 1000.0, currency, date(2026, 3, 5), '', '1',
                                                self.env.company)
        self.assertIn('MILLE', values['amount_in_words_2'])
        self.assertIn('THOUSAND', values['amount_in_words'])
        void = check_format._get_field_values('Partner', 1000.0, currency, date(2026, 3, 5), '', '1',
                                              self.env.company, void=True)
        self.assertFalse(void['amount_in_words_2'])

        check_format.words_lang = 'fr_FR'
        self.assertIn('MILLE', check_format._format_words(1000.0, currency), 'the words follow the format')

    def test_micr_line(self):
        check_format = self.env.ref('om_account_check_printing.check_format_us_ca_leaf').copy({'name': 'Blank'})
        with self.assertRaises(ValidationError):
            check_format.print_micr = True
        check_format.write({'print_micr': True, 'micr_font': base64.b64encode(b'not really a font').decode()})
        self.assertEqual(check_format._format_micr('000123', '011000015', '12-3456-789'),
                         'C000123C A011000015A 123456789C')
        with self.assertRaises(UserError):
            check_format._format_micr('1', '12345', '123')
        with self.assertRaises(UserError):
            check_format._format_micr('1', '011000015', '')

        check_format.micr_style = 'ca'
        self.assertEqual(check_format._format_micr('42', '12345-001', '1234567'), 'C42C A12345D001A 1234567C')
        self.assertEqual(check_format._format_micr('42', '000112345', '1234567'), 'C42C A12345D001A 1234567C',
                         'the electronic form 0 + institution + transit')
        with self.assertRaises(UserError):
            check_format._format_micr('42', '12345', '1234567')

        check_format.micr_style = 'us'
        self.bank.check_format_id = check_format
        with self.assertRaises(UserError):
            check_format._get_field_values('Partner', 1.0, self.env.company.currency_id, date(2026, 3, 5), '', '1',
                                           self.env.company, bank_account=self.env['res.partner.bank'])
        self.bank.bank_account_id = self.env['res.partner.bank'].create({
            'partner_id': self.env.company.partner_id.id,
            'account_number': '555-666-777',
            'clearing_number': '011000015',
        })
        bill, payment = self._pay_bill()
        payment.print_checks()
        report = self.env.ref(LAYOUT).with_context(om_check_format_id=check_format.id)
        html = report._render_qweb_html(report.report_name, payment.ids)[0].decode()
        micr = 'C%sC A011000015A 555666777C' % re.sub(r'[^0-9]', '', payment.check_number)
        self.assertIn(micr, html)
        self.assertIn("font-family: 'OmCheckMicr%d'" % check_format.id, html)
        self.assertIn("@font-face { font-family: 'OmCheckMicr%d'" % check_format.id, html, 'the CSS is not escaped')
        self.assertIn('top: 79.87mm', html, '3/16 inch above the bottom of the cheque, less the font height')

        test = self.env.ref('om_account_check_printing.action_report_check_test')
        html = test.with_context(om_check_format_id=check_format.id)._render_qweb_html(
            test.report_name, check_format.ids)[0].decode()
        self.assertIn('C000123C A011000015A 1234567890C', html)

    def test_no_micr_without_the_option(self):
        bill, payment = self._pay_bill()
        self.bank.check_format_id = self.leaf_format
        report = self.env.ref(LAYOUT).with_context(om_check_format_id=self.leaf_format.id)
        html = report._render_qweb_html(report.report_name, payment.ids)[0].decode()
        self.assertNotIn('o_om_check_micr', html)
        self.assertNotIn('@font-face', html)
