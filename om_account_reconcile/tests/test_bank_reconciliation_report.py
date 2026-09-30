from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBankReconciliationReport(AccountTestInvoicingCommon):
    """ What the bank has seen, against what the books have recorded. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data['default_journal_bank']
        cls.env.company.om_reconcile_auto = False
        # Odoo 18 only writes a journal entry for a payment that has an outstanding
        # account, and the report is about exactly those accounts, so they are set here
        cls.receipts = cls.env['account.account'].create({
            'code': 'OUTREC', 'name': 'Outstanding Receipts', 'account_type': 'asset_current',
            'reconcile': True,
        })
        cls.payments = cls.env['account.account'].create({
            'code': 'OUTPAY', 'name': 'Outstanding Payments', 'account_type': 'asset_current',
            'reconcile': True,
        })
        for line in cls.bank_journal.inbound_payment_method_line_ids:
            line.payment_account_id = cls.receipts
        for line in cls.bank_journal.outbound_payment_method_line_ids:
            line.payment_account_id = cls.payments

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _paid(self, amount, move_type='out_invoice', date='2026-03-01'):
        """ An invoice or a bill, settled by a payment that has not cleared the bank. """
        invoice = self.init_invoice(move_type, amounts=[amount], invoice_date=date,
                                    taxes=[], post=True)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids
        ).create({'journal_id': self.bank_journal.id, 'payment_date': date}).action_create_payments()
        return invoice

    def _statement(self, date='2026-12-31', **values):
        wizard = self.env['om.bank.reconciliation.report'].create({
            'date': date, 'journal_ids': [(6, 0, self.bank_journal.ids)], **values,
        })
        data = {'form': wizard.read(
            ['date', 'journal_ids', 'target_move', 'show_details', 'company_id'])[0]}
        values = self.env['report.om_account_reconcile.report_bank_reconciliation']._get_report_values(
            wizard.ids, data)
        return wizard, values['sections'][0]

    # -------------------------------------------------------------------------
    # The reconciliation
    # -------------------------------------------------------------------------

    def test_a_payment_that_has_not_cleared_is_an_uncleared_receipt(self):
        self._paid(1000.0)

        __, section = self._statement()

        self.assertEqual(section['receipts'], 1000.0)
        self.assertEqual(section['book_balance'], section['ledger'] + 1000.0,
                         'the cash the books believe in is the ledger plus what has not cleared')

    def test_money_paid_out_pulls_the_other_way(self):
        self._paid(1000.0)
        self._paid(400.0, move_type='in_invoice')

        __, section = self._statement()

        self.assertEqual(section['receipts'], 1000.0)
        self.assertEqual(section['payments'], -400.0)
        self.assertEqual(section['book_balance'], section['ledger'] + 600.0)

    def test_clearing_the_payment_takes_it_off_the_statement(self):
        """ Once the bank shows it, it is no longer a reconciling item. """
        self._paid(1000.0)
        uncleared = self.env['account.move.line'].search([
            ('account_id', '=', self.receipts.id), ('reconciled', '=', False)])
        self.assertTrue(uncleared, 'the payment should be sitting in outstanding receipts')

        # the bank reports the receipt, and it is matched against the payment
        transaction = self.env['account.bank.statement.line'].create({
            'journal_id': self.bank_journal.id, 'date': '2026-03-05',
            'payment_ref': 'Customer receipt', 'amount': 1000.0,
        })
        counterpart = transaction.move_id.line_ids.filtered(
            lambda line: line.account_id == self.bank_journal.suspense_account_id)
        counterpart.account_id = self.receipts
        (counterpart + uncleared).reconcile()

        __, section = self._statement()

        self.assertEqual(section['receipts'], 0.0)
        self.assertEqual(section['book_balance'], section['ledger'],
                         'with nothing uncleared the two balances meet')

    def test_the_date_is_a_cut_off(self):
        self._paid(1000.0, date='2026-03-01')
        self._paid(250.0, date='2026-07-01')

        __, section = self._statement(date='2026-04-30')

        self.assertEqual(section['receipts'], 1000.0, 'the July receipt is after the cut-off')

    # -------------------------------------------------------------------------
    # The schedules
    # -------------------------------------------------------------------------

    def test_the_schedules_add_up_to_the_summary(self):
        """ The detail is the evidence for the totals, so it has to agree with them. """
        self._paid(1000.0)
        self._paid(250.0, date='2026-04-01')
        self._paid(400.0, move_type='in_invoice')

        __, section = self._statement()

        self.assertEqual(sum(section['receipt_lines'].mapped('amount_residual')), section['receipts'])
        self.assertEqual(sum(section['payment_lines'].mapped('amount_residual')), section['payments'])
        self.assertEqual(len(section['receipt_lines']), 2)

    def test_journals_sharing_an_outstanding_account_do_not_claim_each_other(self):
        """A company normally has one Outstanding Receipts account for every journal.

        Reading that account alone would hand every journal the whole balance, so each
        section would overstate the cash and the sections would not add up to the
        company's position.
        """
        cash_journal = self.env['account.journal'].create({
            'name': 'Petty Cash', 'code': 'CSH9', 'type': 'cash',
        })
        # the same outstanding accounts as the bank journal, as Odoo sets up by default
        for line in cash_journal.inbound_payment_method_line_ids:
            line.payment_account_id = self.receipts
        for line in cash_journal.outbound_payment_method_line_ids:
            line.payment_account_id = self.payments

        self._paid(1000.0)                                   # through the bank journal
        invoice = self.init_invoice('out_invoice', amounts=[70.0], invoice_date='2026-03-01',
                                    taxes=[], post=True)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids
        ).create({'journal_id': cash_journal.id,
                  'payment_date': '2026-03-01'}).action_create_payments()

        wizard = self.env['om.bank.reconciliation.report'].create({
            'date': '2026-12-31',
            'journal_ids': [(6, 0, (self.bank_journal + cash_journal).ids)],
        })
        data = {'form': wizard.read(
            ['date', 'journal_ids', 'target_move', 'show_details', 'company_id'])[0]}
        sections = self.env['report.om_account_reconcile.report_bank_reconciliation'] \
            ._get_report_values(wizard.ids, data)['sections']
        receipts = {section['journal'].code: section['receipts'] for section in sections}

        self.assertEqual(receipts[self.bank_journal.code], 1000.0)
        self.assertEqual(receipts['CSH9'], 70.0, 'the cash journal must not claim the bank receipt')

    def test_it_opens_on_the_bank_journals_only(self):
        """Cash has no statement to reconcile against, so a cash section would only
        restate the ledger balance. It stays selectable, but it is not offered."""
        cash_journal = self.env['account.journal'].create({
            'name': 'Petty Cash 2', 'code': 'CSH8', 'type': 'cash',
        })
        wizard = self.env['om.bank.reconciliation.report'].create({'date': '2026-12-31'})

        self.assertIn(self.bank_journal, wizard.journal_ids)
        self.assertNotIn(cash_journal, wizard.journal_ids)
        self.assertTrue(all(journal.type == 'bank' for journal in wizard.journal_ids))

    def test_a_cash_journal_is_described_as_cash(self):
        """If one is chosen anyway, it must not claim to be reconciled to a bank."""
        cash_journal = self.env['account.journal'].create({
            'name': 'Petty Cash 3', 'code': 'CSH7', 'type': 'cash',
        })
        wizard = self.env['om.bank.reconciliation.report'].create({
            'date': '2026-12-31', 'journal_ids': [(6, 0, cash_journal.ids)],
        })
        data = {'form': wizard.read(
            ['date', 'journal_ids', 'target_move', 'show_details', 'company_id'])[0]}
        section = self.env['report.om_account_reconcile.report_bank_reconciliation'] \
            ._get_report_values(wizard.ids, data)['sections'][0]

        self.assertTrue(section['is_cash'])

    # -------------------------------------------------------------------------
    # What it says when it cannot reconcile
    # -------------------------------------------------------------------------

    def test_a_journal_without_outstanding_accounts_is_reported_not_guessed(self):
        """ Payments on such a journal never reach the ledger, so a total would lie. """
        self.bank_journal.inbound_payment_method_line_ids.payment_account_id = False
        self.bank_journal.outbound_payment_method_line_ids.payment_account_id = False

        __, section = self._statement()

        self.assertTrue(section['misconfigured'])

    def test_without_statements_it_falls_back_to_the_ledger_and_says_so(self):
        self._paid(1000.0)

        __, section = self._statement()

        self.assertTrue(section['opening_is_ledger'])
        self.assertEqual(section['opening'], section['ledger'])

    def test_a_statement_becomes_the_opening_figure(self):
        statement = self.env['account.bank.statement'].create({
            'name': 'December', 'date': '2026-12-01',
            'line_ids': [(0, 0, {
                'journal_id': self.bank_journal.id, 'date': '2026-12-01',
                'payment_ref': 'Opening', 'amount': 150.0,
            })],
        })
        statement.balance_end_real = statement.balance_end

        __, section = self._statement()

        self.assertFalse(section['opening_is_ledger'])
        self.assertEqual(section['opening'], statement.balance_end_real)

    # -------------------------------------------------------------------------
    # Printing
    # -------------------------------------------------------------------------

    def test_printing_returns_a_report_action(self):
        wizard = self.env['om.bank.reconciliation.report'].create({
            'date': '2026-12-31', 'journal_ids': [(6, 0, self.bank_journal.ids)],
        })

        action = wizard.action_print()

        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'om_account_reconcile.report_bank_reconciliation')

    def test_the_figures_reach_the_printed_page(self):
        self._paid(1234.0)
        wizard = self.env['om.bank.reconciliation.report'].create({
            'date': '2026-12-31', 'journal_ids': [(6, 0, self.bank_journal.ids)],
        })
        action = wizard.action_print()

        html, __ = self.env['ir.actions.report']._render_qweb_html(
            'om_account_reconcile.report_bank_reconciliation', wizard.ids, data=action['data'])
        body = html.decode() if isinstance(html, bytes) else str(html)

        # the amount, not the heading: a section that rendered nothing would still
        # leave its title on the page
        self.assertIn('1,234.00', body)
        self.assertIn(self.bank_journal.name, body)
