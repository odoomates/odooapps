from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAccountAudit(AccountTestInvoicingCommon):

    def test_integrity_check_finds_changed_entries(self):
        company = self.company_data['company']
        self.company_data['default_journal_sale'].restrict_mode_hash_table = True
        invoice = self.init_invoice('out_invoice', amounts=[100], invoice_date='2024-01-15', post=True)
        self.assertTrue(invoice.inalterable_hash)
        Check = self.env['account.integrity.check']
        self.assertEqual(Check._run(company).state, 'verified')

        self.env.cr.execute("UPDATE account_move SET inalterable_hash = 'changed' WHERE id = %s", [invoice.id])
        self.env.invalidate_all()
        check = Check._run(company)
        self.assertEqual(check.state, 'corrupted')
        self.assertTrue(check.activity_ids, 'the accounting administrators are asked to look at it')

        pack = self.env['account.audit.pack'].create({
            'company_id': company.id, 'date_from': '2024-01-01', 'date_to': '2024-01-31', 'run_check': False})
        html = self.env['ir.actions.report']._render_qweb_html('om_account_audit.report_audit_pack', pack.ids)[0]
        self.assertIn(b'Corrupted', html)

    def test_closing_secures_the_entries(self):
        company = self.company_data['company']
        company.om_audit_secure_on_close = True
        invoice = self.init_invoice('out_invoice', amounts=[100], invoice_date='2024-01-15', post=True)
        self.assertFalse(invoice.inalterable_hash)
        closing = self.env['account.period.closing'].create({
            'company_id': company.id, 'date_from': '2024-01-01', 'lock_type': 'sale_purchase'})
        closing.check_ids.filtered('is_manual').action_mark_done()
        closing.action_close()
        self.assertEqual(closing.state, 'closed')
        self.assertTrue(invoice.inalterable_hash, 'the entries of the period are secured')
