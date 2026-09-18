import io
import zipfile

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
@freeze_time('2026-03-01')
class TestStatements(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.external_report_layout_id = cls.env.ref('web.external_layout_standard')
        cls.partner = cls.env['res.partner'].create({'name': 'Trade Partner', 'email': 'trade@example.com'})
        cls.invoice = cls.init_invoice('out_invoice', partner=cls.partner, invoice_date='2026-01-01',
                                       amounts=[1000.0], post=True)
        cls.bill = cls.init_invoice('in_invoice', partner=cls.partner, invoice_date='2026-03-10',
                                    amounts=[400.0], post=True)
        cls.old_bill = cls.init_invoice('in_invoice', partner=cls.partner, invoice_date='2026-01-10',
                                        amounts=[250.0], post=True)

    def test_vendor_statement_lists_the_open_bills(self):
        groups = self.partner._followup_statement_lines(statement_type='vendor')
        self.assertEqual(len(groups), 1)
        lines = groups[0]['lines']
        self.assertEqual({line['move'] for line in lines}, set(self.bill | self.old_bill))
        # what is owed to the vendor is positive
        self.assertEqual(groups[0]['total'], self.bill.amount_total + self.old_bill.amount_total)
        self.assertEqual(groups[0]['total_overdue'], self.old_bill.amount_total)
        # the customer statement keeps the invoices only
        customer_groups = self.partner._followup_statement_lines()
        self.assertEqual({line['move'] for line in customer_groups[0]['lines']}, set(self.invoice))

        html = self.env['ir.actions.report']._render_qweb_html(
            'om_account_followup.report_vendor_statement', self.partner.ids)[0].decode()
        self.assertIn('Vendor Statement', html)
        self.assertIn(self.bill.name, html)
        self.assertNotIn(self.invoice.name, html)
        self.assertNotIn('If you have already paid', html)

        action = self.partner.action_print_vendor_statement()
        self.assertEqual(action['report_name'], 'om_account_followup.report_vendor_statement')

    def test_nothing_open_is_refused(self):
        partner = self.env['res.partner'].create({'name': 'Nothing Open'})
        for method in ('action_print_vendor_statement', 'action_send_vendor_statement',
                       'action_vendor_statement_xlsx', 'action_send_customer_statement',
                       'action_customer_statement_xlsx'):
            with self.assertRaises(UserError, msg=method):
                getattr(partner, method)()

    def test_send_statement_attaches_the_pdf(self):
        for statement_type, report in (('customer', 'Statement'), ('vendor', 'Vendor Statement')):
            action = getattr(self.partner, f'action_send_{statement_type}_statement')()
            self.assertEqual(action['res_model'], 'mail.compose.message')
            composer = self.env['mail.compose.message'].with_context(action['context']).create({})
            self.assertEqual(composer.composition_mode, 'comment')
            composer._action_send_mail()
            message = self.partner.message_ids[0]
            self.assertIn('Statement of Account', message.subject)
            # the tests render the reports in html instead of pdf
            self.assertEqual(message.attachment_ids.mapped(lambda attachment: attachment.name.rsplit('.', 1)[0]),
                             [f'{report} - Trade Partner'])

        # several partners: one email each
        other = self.env['res.partner'].create({'name': 'Other Customer', 'email': 'other@example.com'})
        self.init_invoice('out_invoice', partner=other, invoice_date='2026-02-01', amounts=[50.0], post=True)
        action = (self.partner | other).action_send_customer_statement()
        self.assertEqual(action['context']['default_composition_mode'], 'mass_mail')

    def test_statement_in_excel(self):
        content = self.partner._statement_xlsx('vendor')
        with zipfile.ZipFile(io.BytesIO(content)) as xlsx:
            strings = xlsx.read('xl/sharedStrings.xml').decode()
            self.assertIn('xl/worksheets/sheet1.xml', xlsx.namelist())
        self.assertIn('Vendor Statement', strings)
        self.assertIn(self.bill.name, strings)
        self.assertNotIn(self.invoice.name, strings)



@tagged('post_install', '-at_install')
class TestStatementDownload(AccountTestInvoicingCommon, HttpCase):

    def test_download_statement_in_excel(self):
        partner = self.env['res.partner'].create({'name': 'Trade Partner'})
        invoice = self.init_invoice('out_invoice', partner=partner, invoice_date='2026-01-01',
                                    amounts=[1000.0], post=True)
        new_test_user(self.env, login='statement_accountant',
                      groups='base.group_user,account.group_account_invoice',
                      company_id=self.env.company.id)
        new_test_user(self.env, login='statement_employee', groups='base.group_user',
                      company_id=self.env.company.id)
        action = partner.action_customer_statement_xlsx()

        self.authenticate('statement_accountant', 'statement_accountant')
        response = self.url_open(action['url'])
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response.headers['Content-Type'])
        self.assertIn('Customer%20Statement', response.headers['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as xlsx:
            strings = xlsx.read('xl/sharedStrings.xml').decode()
        self.assertIn(invoice.name, strings)
        self.assertEqual(self.url_open(
            f'/om_account_followup/statement/unknown/xlsx?partner_ids={partner.id}').status_code, 404)

        # the statements are for the users with access to the invoices
        self.authenticate('statement_employee', 'statement_employee')
        self.assertEqual(self.url_open(action['url']).status_code, 404)
