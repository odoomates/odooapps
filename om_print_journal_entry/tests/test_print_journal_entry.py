from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPrintJournalEntry(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.init_invoice('out_invoice', partner=cls.partner_a, amounts=[1000.0],
                                       invoice_date='2026-03-01', taxes=cls.tax_sale_a, post=True)
        # a miscellaneous entry, without taxes
        cls.plain = cls.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': cls.company_data['default_journal_misc'].id,
            'date': '2026-03-01',
            'line_ids': [
                (0, 0, {'name': 'Debit line', 'account_id': cls.company_data['default_account_receivable'].id,
                        'partner_id': cls.partner_a.id, 'debit': 500.0}),
                (0, 0, {'name': 'Credit line', 'account_id': cls.company_data['default_account_revenue'].id,
                        'credit': 500.0}),
            ],
        })
        cls.plain.action_post()

    def _page(self, move):
        html, __ = self.env['ir.actions.report']._render_qweb_html(
            'om_print_journal_entry.report_journal_entries', move.ids)
        return html.decode() if isinstance(html, bytes) else str(html)

    def test_the_entry_prints_its_details(self):
        page = self._page(self.invoice)
        for text in (self.invoice.name, self.invoice.journal_id.name, self.partner_a.name, 'Due Date'):
            self.assertIn(text, page)

    def test_the_taxes_column_and_the_tax_summary(self):
        page = self._page(self.invoice)
        self.assertIn('>Taxes</th>', page)
        self.assertIn('Tax Summary', page)
        self.assertIn(self.tax_sale_a.name, page)
        summary = self.invoice.om_print_tax_summary()
        self.assertEqual(len(summary), 1)
        self.assertAlmostEqual(summary[0]['base'], 1000.0)
        self.assertAlmostEqual(summary[0]['amount'], self.invoice.amount_tax)

    def test_no_taxes_no_tax_column(self):
        page = self._page(self.plain)
        self.assertIn('Debit line', page)
        self.assertNotIn('>Taxes</th>', page)
        self.assertNotIn('Tax Summary', page)
