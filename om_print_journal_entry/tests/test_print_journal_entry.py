from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestPrintJournalEntry(common.TransactionCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        self.journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
        accounts = self.env['account.account'].search([('company_id', '=', company.id)], limit=2)
        if not self.journal or len(accounts) < 2:
            self.skipTest('no chart of accounts on this company')
        self.move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'ref': 'Printed entry',
            'line_ids': [
                (0, 0, {'account_id': accounts[0].id, 'name': 'Debit line', 'debit': 123.45}),
                (0, 0, {'account_id': accounts[1].id, 'name': 'Credit line', 'credit': 123.45}),
            ],
        })
        self.report = self.env.ref('om_print_journal_entry.action_report_journal_entries')

    def test_the_print_is_offered_on_journal_entries(self):
        self.assertEqual(self.report.model, 'account.move')
        self.assertEqual(self.report.binding_model_id.model, 'account.move')
        self.assertEqual(self.report.binding_type, 'report')

    def test_the_entry_prints_its_lines_and_totals(self):
        html = self.report._render_qweb_html(self.move.ids)[0].decode()
        for text in (self.move.name, 'Printed entry', 'Debit line', 'Credit line', self.journal.name):
            self.assertIn(text, html)
        self.assertIn('123.45', html)
