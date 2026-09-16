from datetime import date

from odoo.exceptions import RedirectWarning, ValidationError
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
        cls.check_method = cls.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == 'check_printing')
        cls.a4_format = cls.env.ref('om_account_check_printing.check_format_a4_top')
        cls.leaf_format = cls.env.ref('om_account_check_printing.check_format_leaf')

    def _pay_bill(self, amount=1234.5):
        bill = self.init_invoice('in_invoice', amounts=[amount], taxes=[], invoice_date='2026-03-01', post=True)
        payments = self.env['account.payment.register'].with_context(active_model='account.move', active_ids=bill.ids).create({
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
        self.assertEqual(self.env.ref(LAYOUT).with_context(om_check_format_id=self.a4_format.id).get_paperformat().format, 'A4')

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
        html = report.with_context(om_check_format_id=check_format.id)._render_qweb_html(report.report_name, check_format.ids)[0].decode()
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
