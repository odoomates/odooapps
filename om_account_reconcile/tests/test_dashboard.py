from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestDashboard(AccountTestInvoicingCommon):
    """ The bank and cash cards of the dashboard: what is left to do on the account, and typing transactions in. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.om_reconcile_auto = False
        cls.bank = cls.company_data['default_journal_bank']
        cls.cash = cls.company_data['default_journal_cash']

    def _dashboard(self, journal):
        return journal._get_journal_dashboard_data_batched()[journal.id]

    def test_new_transaction(self):
        action = self.bank.om_action_new_transaction()
        self.assertEqual((action['res_model'], action['target']), ('account.bank.statement.line', 'new'))
        view = self.env['ir.ui.view'].browse(action['views'][0][0])
        with Form(self.env['account.bank.statement.line'].with_context(action['context']), view=view) as form:
            form.payment_ref = 'Bank fee'
            form.amount = -12.5
        st_line = form.record
        self.assertEqual(st_line.journal_id, self.bank)
        self.assertFalse(st_line.is_reconciled)
        self.assertEqual(self._dashboard(self.bank)['number_to_reconcile'], 1)

        action = st_line.om_action_reconcile()
        self.assertEqual(action['tag'], 'om_bank_reconciliation')
        self.assertEqual(action['params'], {'journal_id': self.bank.id, 'filter': 'all', 'st_line_id': st_line.id})

    def test_new_cash_statement(self):
        action = self.cash.om_action_new_statement()
        view = self.env['ir.ui.view'].browse(action['views'][0][0])
        with Form(self.env['account.bank.statement'].with_context(action['context']), view=view) as form:
            form.name = 'Cash of the day'
            with form.line_ids.new() as line:
                line.payment_ref = 'Coffee'
                line.amount = -3.0
            with form.line_ids.new() as line:
                line.payment_ref = 'Counter sale'
                line.amount = 10.0
            form.balance_end_real = 7.0
        statement = form.record
        self.assertEqual(statement.journal_id, self.cash)
        self.assertEqual(statement.line_ids.journal_id, self.cash)
        self.assertEqual(statement.balance_end, 7.0)
        self.assertTrue(statement.is_complete)

        data = self._dashboard(self.cash)
        self.assertTrue(data['has_at_least_one_statement'])
        self.assertEqual(data['number_to_reconcile'], 2)
        action = self.cash.om_action_open_last_statement()
        self.assertEqual((action['res_model'], action['res_id']), ('account.bank.statement', statement.id))

    def test_transactions_to_review(self):
        st_line = self.env['account.bank.statement.line'].create({
            'journal_id': self.bank.id, 'date': '2026-01-20', 'amount': 50.0, 'payment_ref': 'Unknown deposit',
        })
        st_line.move_id.review_state = 'todo'
        self.assertEqual(self._dashboard(self.bank)['number_to_check'], 1)
        action = self.bank.om_action_open_to_review()
        self.assertEqual(action['params']['filter'], 'to_review')
        found = self.env['account.bank.statement.line'].om_bank_rec_search_transactions(
            journal_id=self.bank.id, state='to_review')
        self.assertEqual([tr['id'] for tr in found['transactions']], st_line.ids)

    def test_dashboard_view(self):
        arch = self.env['account.journal'].get_views(
            [(self.env.ref('account.account_journal_dashboard_kanban_view').id, 'kanban')])['views']['kanban']['arch']
        for marker in ('o_om_dashboard_reconcile', 'o_om_dashboard_new_transaction', 'o_om_dashboard_new_statement',
                       'o_om_dashboard_last_statement', 'o_om_dashboard_to_review'):
            self.assertIn(marker, arch)
