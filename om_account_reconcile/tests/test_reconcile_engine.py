from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestReconcileEngine(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.misc_journal = cls.company_data['default_journal_misc']
        cls.expense_account = cls.company_data['default_account_expense']
        cls.income_account = cls.company_data['default_account_revenue']
        cls.purchase_tax = cls.env['account.tax'].create({
            'name': 'Purchase 15%', 'amount': 15.0, 'type_tax_use': 'purchase',
        })
        cls.env.company.om_reconcile_auto = False

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _invoice(self, amount, move_type='out_invoice', partner=None, currency=None, date='2026-01-10'):
        return self.init_invoice(move_type, partner=partner or self.partner_a, amounts=[amount], taxes=[],
                                 invoice_date=date, currency=currency, post=True)

    def _open_line(self, move):
        return move.line_ids.filtered(
            lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable'))

    def _transaction(self, amount, label='Transaction', partner=None, date='2026-01-20', **values):
        return self.env['account.bank.statement.line'].create({
            'journal_id': self.bank_journal.id,
            'date': date,
            'payment_ref': label,
            'amount': amount,
            'partner_id': (partner or self.partner_a).id if partner is not False else False,
            **values,
        })

    def _entry_lines(self, st_line):
        return sorted(
            [(line.account_id.id, line.balance) for line in st_line.move_id.line_ids],
            key=lambda item: (item[0], item[1]))

    # -------------------------------------------------------------------------
    # Transactions
    # -------------------------------------------------------------------------

    def test_invoice_full_and_undo(self):
        invoice = self._invoice(1000.0)
        st_line = self._transaction(1000.0)
        st_line._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})
        self.assertTrue(st_line.is_reconciled)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertFalse(st_line.move_id.line_ids.filtered(
            lambda line: line.account_id == self.bank_journal.suspense_account_id))

        st_line._om_undo()
        self.assertFalse(st_line.is_reconciled)
        self.assertEqual(invoice.payment_state, 'not_paid')

        with self.assertRaises(UserError):
            st_line._om_reconcile({})

    def test_payment_in_process(self):
        outstanding = self.env['account.account'].create({
            'code': 'OUTREC', 'name': 'Outstanding Receipts', 'account_type': 'asset_current', 'reconcile': True,
        })
        self.bank_journal.inbound_payment_method_line_ids.payment_account_id = outstanding
        invoice = self._invoice(500.0)
        payment = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'payment_date': '2026-01-12', 'journal_id': self.bank_journal.id})._create_payments()
        self.assertFalse(payment.is_matched)

        st_line = self._transaction(500.0)
        outstanding_line = payment.move_id.line_ids.filtered(lambda line: line.account_id == outstanding)
        self.assertIn(outstanding_line, st_line._om_search_candidates())
        st_line._om_reconcile({'matches': [{'aml_id': outstanding_line.id}]})
        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(payment.is_matched)

    def test_partial_transactions(self):
        invoice = self._invoice(1000.0)
        first = self._transaction(400.0)
        first._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})
        self.assertTrue(first.is_reconciled)
        self.assertEqual(invoice.amount_residual, 600.0)

        second = self._transaction(600.0)
        second._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})
        self.assertTrue(second.is_reconciled)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))

    def test_partial_amount_of_an_item(self):
        invoice = self._invoice(1000.0)
        st_line = self._transaction(1000.0)
        st_line._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id, 'amount': 250.0}]})
        self.assertFalse(st_line.is_reconciled)
        self.assertEqual(st_line.amount_residual, -750.0)
        self.assertEqual(invoice.amount_residual, 750.0)

    def test_several_invoices_one_transaction(self):
        invoices = self._invoice(300.0) + self._invoice(700.0)
        st_line = self._transaction(1000.0)
        st_line._om_reconcile({'matches': [{'aml_id': line.id} for line in self._open_line(invoices)]})
        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(all(state in ('paid', 'in_payment') for state in invoices.mapped('payment_state')))

    def test_overpayment_then_writeoff(self):
        invoice = self._invoice(1000.0)
        st_line = self._transaction(1200.0)
        st_line._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})
        self.assertFalse(st_line.is_reconciled)
        self.assertEqual(st_line.amount_residual, -200.0)

        st_line._om_reconcile({'writeoffs': [
            {'account_id': self.income_account.id, 'amount': -200.0, 'label': 'Extra'}]})
        self.assertTrue(st_line.is_reconciled)
        self.assertIn((self.income_account.id, -200.0), self._entry_lines(st_line))

    def test_writeoff_with_taxes(self):
        for tax_included, amount in ((True, 115.0), (False, 100.0)):
            with self.subTest(tax_included=tax_included):
                st_line = self._transaction(-115.0, label='Bank fee', partner=False)
                st_line._om_reconcile({'writeoffs': [{
                    'account_id': self.expense_account.id, 'amount': amount, 'label': 'Bank fee',
                    'tax_ids': self.purchase_tax.ids, 'tax_included': tax_included,
                }]})
                self.assertTrue(st_line.is_reconciled)
                lines = st_line.move_id.line_ids
                self.assertEqual(lines.filtered(
                    lambda line: line.account_id == self.expense_account
                    and not line.tax_repartition_line_id).balance, 100.0)
                tax_line = lines.filtered('tax_repartition_line_id')
                self.assertEqual(tax_line.balance, 15.0)
                self.assertEqual(tax_line.tax_line_id, self.purchase_tax)

    def test_foreign_currency_invoice(self):
        # rate 2.0: 200 foreign currency = 100 company currency
        other_currency = self.setup_other_currency('EUR')
        invoice = self._invoice(200.0, currency=other_currency)
        st_line = self._transaction(100.0)
        proposal = {'matches': [{'aml_id': self._open_line(invoice).id}]}
        self.assertTrue(st_line._om_is_complete(proposal))
        st_line._om_reconcile(proposal)
        self.assertTrue(st_line.is_reconciled)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))

    def test_foreign_currency_transaction(self):
        other_currency = self.setup_other_currency('EUR')
        invoice = self._invoice(200.0, currency=other_currency)
        # the bank received 200 EUR for 90 in company currency: the bank rate differs from the one of the invoice
        st_line = self._transaction(90.0, foreign_currency_id=other_currency.id, amount_currency=200.0)
        st_line._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})
        self.assertTrue(st_line.is_reconciled)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        receivable = self._open_line(invoice)
        self.assertTrue(receivable.reconciled)
        exchange_moves = (receivable.matched_debit_ids + receivable.matched_credit_ids).exchange_move_id
        self.assertEqual(abs(sum(exchange_moves.line_ids.filtered(
            lambda line: line.account_id == receivable.account_id).mapped('balance'))), 10.0)

    def test_errors(self):
        invoice = self._invoice(100.0)
        st_line = self._transaction(100.0)
        st_line._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})
        with self.assertRaises(UserError):
            st_line._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})
        other = self._transaction(100.0)
        with self.assertRaises(UserError):
            other._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})

    def test_only_accountants(self):
        invoice = self._invoice(100.0)
        st_line = self._transaction(100.0)
        billing = new_test_user(self.env, login='reco_billing', groups='account.group_account_invoice')
        with self.assertRaises(UserError):
            st_line.with_user(billing)._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})

    # -------------------------------------------------------------------------
    # Candidates
    # -------------------------------------------------------------------------

    def test_suggestions(self):
        older = self._invoice(1000.0, date='2026-01-05')
        referenced = self._invoice(500.0, date='2026-01-06')
        st_line = self._transaction(500.0, label='Payment of %s thanks' % referenced.name)
        scored = st_line._om_scored_candidates()
        self.assertEqual(scored[0][0], self._open_line(referenced))
        self.assertGreaterEqual(scored[0][1], 90)
        self.assertEqual(st_line._om_suggested_proposal()['matches'], [{'aml_id': self._open_line(referenced).id}])

        # no reference: the oldest open items of the partner adding up to the amount
        both = self._transaction(1500.0, label='Transfer')
        proposal = both._om_suggested_proposal()
        self.assertEqual({match['aml_id'] for match in proposal['matches']},
                         set(self._open_line(older + referenced).ids))

        self.assertIn(self._open_line(older), both._om_search_candidates(search=older.name))
        self.assertIn(self._open_line(referenced), both._om_search_candidates(search='500'))

    # -------------------------------------------------------------------------
    # Reconciliation models
    # -------------------------------------------------------------------------

    def test_writeoff_model(self):
        model = self.env['account.reconcile.model'].create({
            'name': 'Bank fees', 'rule_type': 'reco_model', 'match_label': 'contains', 'match_label_param': 'FEE',
            'line_ids': [Command.create({
                'account_id': self.expense_account.id, 'amount_type': 'percentage', 'amount_string': '100'})],
        })
        st_line = self._transaction(-20.0, label='monthly fee', partner=False)
        self.assertTrue(model._om_is_applicable(st_line))
        self.assertFalse(model._om_is_applicable(self._transaction(-20.0, label='rent', partner=False)))
        st_line._om_reconcile(model._om_get_proposal(st_line))
        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(
            st_line.move_id.line_ids.filtered(lambda line: line.account_id == self.expense_account).reconcile_model_id,
            model)

    def test_regex_and_fixed_amounts(self):
        model = self.env['account.reconcile.model'].create({
            'name': 'Commission', 'rule_type': 'reco_model',
            'line_ids': [
                Command.create({'account_id': self.expense_account.id, 'amount_type': 'regex',
                                'amount_string': r'COM ([\d,]+)'}),
                Command.create({'account_id': self.income_account.id, 'amount_type': 'fixed', 'amount_string': '-1'}),
            ],
        })
        st_line = self._transaction(100.0, label='SALE 113,50 COM 12,50', partner=False)
        writeoffs = model._om_get_writeoffs(st_line)
        self.assertEqual([writeoff['amount'] for writeoff in writeoffs], [-12.5, 1.0])

    def test_partner_mapping_and_matching_rule(self):
        partner = self.partner_b
        self.env['account.reconcile.model'].create({
            'name': 'ACME mapping', 'rule_type': 'reco_model', 'trigger': 'manual',
            'match_label': 'contains', 'match_label_param': 'ACME',
            'line_ids': [Command.create({'partner_id': partner.id, 'amount_string': '100'})],
        })
        self.env['account.reconcile.model'].create({
            'name': 'Invoices with 2% tolerance', 'rule_type': 'matching_rule',
            'payment_tolerance': 2.0, 'payment_tolerance_type': 'percentage',
            'line_ids': [Command.create({
                'account_id': self.expense_account.id, 'amount_type': 'percentage', 'amount_string': '100'})],
        })
        invoice = self._invoice(1000.0, partner=partner)
        st_line = self._transaction(990.0, label='ACME TRANSFER', partner=False)
        reconciled = st_line._om_auto_reconcile()
        self.assertEqual(reconciled, st_line)
        self.assertEqual(st_line.partner_id, partner)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertIn((self.expense_account.id, 10.0), self._entry_lines(st_line))

    def test_auto_reconcile_new_transactions(self):
        invoice = self._invoice(250.0)
        self.env.company.om_reconcile_auto = True
        perfect = self._transaction(250.0, label='%s' % invoice.name)
        ambiguous = self._transaction(250.0, label='no reference')
        self.env['account.bank.statement.line']._om_cron_auto_reconcile()
        self.assertTrue(perfect.is_reconciled)
        self.assertFalse(ambiguous.is_reconciled)
        self.assertTrue(ambiguous.om_auto_processed)

        self.env.company.om_reconcile_auto = False
        other_invoice = self._invoice(80.0)
        untouched = self._transaction(80.0, label=other_invoice.name)
        self.env['account.bank.statement.line']._om_cron_auto_reconcile()
        self.assertFalse(untouched.is_reconciled)

    # -------------------------------------------------------------------------
    # Journal items
    # -------------------------------------------------------------------------

    def test_match_journal_items(self):
        invoice = self._invoice(1000.0)
        refund = self._invoice(1000.0, move_type='out_refund')
        suggestions = self.env['account.move.line']._om_suggest_item_matches([('partner_id', '=', self.partner_a.id)])
        self.assertIn(self._open_line(invoice + refund), suggestions)
        self._open_line(invoice + refund)._om_reconcile_items()
        self.assertTrue(all(self._open_line(invoice + refund).mapped('reconciled')))

    def test_match_journal_items_with_writeoff(self):
        invoice = self._invoice(1000.0)
        receivable = self._open_line(invoice)
        entry = self.env['account.move'].create({
            'journal_id': self.misc_journal.id, 'date': '2026-01-15',
            'line_ids': [
                Command.create({'account_id': receivable.account_id.id, 'partner_id': self.partner_a.id,
                                'balance': -990.0}),
                Command.create({'account_id': self.income_account.id, 'balance': 990.0}),
            ],
        })
        entry.action_post()
        items = receivable + entry.line_ids.filtered(lambda line: line.account_id == receivable.account_id)
        self.assertEqual(items._om_matching_summary()['difference'], 10.0)
        with self.assertRaises(UserError):
            (items + entry.line_ids.filtered(lambda line: line.account_id == self.income_account))._om_reconcile_items()

        items._om_reconcile_items(writeoff={
            'account_id': self.expense_account.id, 'journal_id': self.misc_journal.id,
            'date': '2026-01-31', 'label': 'Discount',
        })
        self.assertTrue(all(items.mapped('reconciled')))
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))

    def test_administrator_without_accounting_features(self):
        invoice = self._invoice(100.0)
        st_line = self._transaction(100.0)
        administrator = new_test_user(self.env, login='reco_invoicing_admin', groups='account.group_account_manager')
        if administrator.has_group('account.group_account_basic'):
            self.skipTest('the administrators have the accounting features in this version')
        with self.assertRaises(UserError):
            st_line.with_user(administrator)._om_reconcile({'matches': [{'aml_id': self._open_line(invoice).id}]})

    # -------------------------------------------------------------------------
    # Screen API
    # -------------------------------------------------------------------------

    def test_screen_api(self):
        invoice = self._invoice(400.0)
        fee_model = self.env['account.reconcile.model'].create({
            'name': 'Fee', 'rule_type': 'reco_model',
            'line_ids': [Command.create({
                'account_id': self.expense_account.id, 'amount_type': 'percentage', 'amount_string': '100'})],
        })
        st_line = self._transaction(390.0, label='Payment %s' % invoice.name)
        StLine = self.env['account.bank.statement.line']
        listed = StLine.om_bank_rec_search_transactions(journal_id=self.bank_journal.id, search=invoice.name)
        self.assertEqual([tr['id'] for tr in listed['transactions']], st_line.ids)

        data = st_line.om_bank_rec_get_data()
        self.assertEqual(data['transaction']['remaining'], 390.0)
        self.assertEqual([match['aml_id'] for match in data['suggestion']['matches']], self._open_line(invoice).ids)
        self.assertIn(fee_model.id, [model['id'] for model in data['models']])
        self.assertIn(self._open_line(invoice).id, [candidate['id'] for candidate in st_line.om_bank_rec_candidates()])

        # the invoice in full: 10 more than received
        proposal = {'matches': [{'aml_id': self._open_line(invoice).id, 'amount': 400.0}], 'writeoffs': []}
        preview = st_line.om_bank_rec_preview(proposal)
        self.assertFalse(preview['is_complete'])
        self.assertEqual(preview['remaining'], 10.0)
        proposal['writeoffs'] = st_line.om_bank_rec_model_writeoffs(fee_model.id, proposal)
        self.assertEqual([writeoff['amount'] for writeoff in proposal['writeoffs']], [10.0])
        self.assertTrue(st_line.om_bank_rec_preview(proposal)['is_complete'])

        data = st_line.om_bank_rec_validate(proposal)
        self.assertTrue(data['transaction']['is_reconciled'])
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertIn(invoice.name, [name for line in data['entry_lines'] for name in line['matched_move_names']])

        data = st_line.om_bank_rec_undo()
        self.assertFalse(data['transaction']['is_reconciled'])

    def test_match_wizard_and_suggestions(self):
        invoice = self._invoice(500.0)
        refund = self._invoice(490.0, move_type='out_refund')
        items = self._open_line(invoice + refund)
        action = items.om_action_match()
        wizard = self.env[action['res_model']].with_context(action['context']).create({})
        self.assertEqual(wizard.difference, 10.0)
        self.assertFalse(wizard.is_balanced)
        wizard.write({'writeoff': True, 'writeoff_account_id': self.expense_account.id})
        wizard.action_reconcile()
        self.assertTrue(all(items.mapped('reconciled')))

        other_invoice = self._invoice(75.0)
        other_refund = self._invoice(75.0, move_type='out_refund')
        self.env['account.move.line'].om_action_match_suggestions(
            [('move_id', 'in', (other_invoice + other_refund).ids)])
        self.assertTrue(all(self._open_line(other_invoice + other_refund).mapped('reconciled')))
