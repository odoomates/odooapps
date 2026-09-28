import time

from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.fields import Domain


class ReportBankReconciliation(models.AbstractModel):
    _name = 'report.om_account_reconcile.report_bank_reconciliation'
    _description = 'Bank Reconciliation Statement'

    # ------------------------------------------------------------------
    # the ledger
    # ------------------------------------------------------------------

    @api.model
    def _line_domain(self, accounts, form, journal=None):
        """ :param journal: restrict to the entries this journal itself posted.

        Companies normally share one Outstanding Receipts account across every bank and
        cash journal, so the account alone does not say which journal an item belongs
        to - without this every journal would claim all of them.
        """
        states = ('posted',) if form['target_move'] == 'posted' else ('draft', 'posted')
        company_id = form['company_id'][0] if isinstance(form['company_id'], (list, tuple)) \
            else form['company_id']
        domain = (Domain('account_id', 'in', accounts.ids)
                  & Domain('company_id', 'child_of', company_id)
                  & Domain('parent_state', 'in', states)
                  & Domain('date', '<=', form['date']))
        if journal is not None:
            domain &= Domain('journal_id', '=', journal.id)
        return domain

    @api.model
    def _balance(self, accounts, form, journal=None):
        """ What the ledger says an account holds at the close of the date. """
        if not accounts:
            return 0.0
        [(balance,)] = self.env['account.move.line']._read_group(
            self._line_domain(accounts, form, journal=journal), aggregates=['balance:sum'])
        return balance or 0.0

    @api.model
    def _uncleared(self, accounts, form, journal=None):
        """ The items sitting on an account that have not been matched off yet.

        Read from ``amount_residual`` rather than ``balance``: a part-cleared item has
        to count for what is left of it, not for what it started as.
        """
        if not accounts:
            return 0.0, self.env['account.move.line']
        lines = self.env['account.move.line'].search(
            self._line_domain(accounts, form, journal=journal) & Domain('reconciled', '=', False),
            order='date, id')
        lines = lines.filtered(lambda line: not line.company_currency_id.is_zero(line.amount_residual))
        return sum(lines.mapped('amount_residual')), lines

    # ------------------------------------------------------------------
    # a journal
    # ------------------------------------------------------------------

    @api.model
    def _journal_section(self, journal, form):
        """ The reconciliation of one bank or cash journal.

        The shape of it: what the bank has told us, plus what we have recorded that the
        bank has not seen yet, gives the cash the books believe we hold.
        """
        currency = journal.currency_id or journal.company_id.currency_id
        inbound = journal.inbound_payment_method_line_ids.payment_account_id
        outbound = journal.outbound_payment_method_line_ids.payment_account_id

        # the bank account is read without a journal filter on purpose: an opening
        # balance or a correction posted from a miscellaneous journal still belongs to
        # the bank balance
        ledger = self._balance(journal.default_account_id, form)
        receipts, receipt_lines = self._uncleared(inbound, form, journal=journal)
        payments, payment_lines = self._uncleared(outbound, form, journal=journal)
        # the suspense account holds the bank's own items that nothing has been matched
        # to yet; it is not reconcilable in every chart, so its plain balance is used
        unmatched = self._balance(journal.suspense_account_id, form, journal=journal)

        statement = self.env['account.bank.statement'].search([
            ('journal_id', '=', journal.id),
            ('date', '<=', form['date']),
        ], order='date desc, id desc', limit=1)

        unmatched_lines = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', journal.id),
            ('date', '<=', form['date']),
            ('is_reconciled', '=', False),
        ], order='date, id')

        return {
            'journal': journal,
            'currency': currency,
            # a cash journal is reconciled against a count, not against a bank
            'is_cash': journal.type == 'cash',
            # a journal with no outstanding account never posts its payments to the
            # ledger at all, so the totals below would be quietly wrong: say so instead
            'misconfigured': not (inbound or outbound),
            'statement': statement,
            'opening': statement.balance_end_real if statement else ledger,
            'opening_is_ledger': not statement,
            'ledger': ledger,
            'receipts': receipts,
            'payments': payments,
            'unmatched': unmatched,
            'book_balance': ledger + receipts + payments,
            'receipt_lines': receipt_lines,
            'payment_lines': payment_lines,
            'unmatched_lines': unmatched_lines,
        }

    # ------------------------------------------------------------------
    # the report
    # ------------------------------------------------------------------

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_('Form content is missing, this report cannot be printed.'))
        form = data['form']
        # the reconciliations are read through the ORM: write the pending changes first
        self.env.flush_all()
        journals = self.env['account.journal'].browse(form.get('journal_ids') or []).exists()
        return {
            'doc_ids': docids,
            'doc_model': 'om.bank.reconciliation.report',
            'docs': self.env['om.bank.reconciliation.report'].browse(docids),
            'data': form,
            'time': time,
            'sections': [self._journal_section(journal, form)
                         for journal in journals.sorted('code')],
        }
