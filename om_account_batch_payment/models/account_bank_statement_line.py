from odoo import fields, models, _
from odoo.tools.misc import format_date

from odoo.addons.om_account_reconcile.models.account_bank_statement_line import (
    SCORE_AMOUNT, SCORE_PERFECT, SCORE_REFERENCE,
)

OPEN_ACCOUNT_TYPES = ('asset_receivable', 'liability_payable')


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    om_batch_payment_ids = fields.Many2many(
        'account.payment', 'om_batch_payment_statement_line_rel', 'statement_line_id', 'payment_id',
        string='Payments Cleared through a Batch', copy=False, readonly=True)

    # -------------------------------------------------------------------------
    # Batches
    # -------------------------------------------------------------------------

    def _om_open_batches(self, search=None):
        """ The sent batches of the bank of the transaction, in the direction of the transaction. """
        self.ensure_one()
        domain = [
            ('journal_id', '=', self.journal_id.id),
            ('state', '=', 'sent'),
            ('batch_type', '=', 'inbound' if self.amount > 0 else 'outbound'),
        ]
        if search:
            domain.append(('name', 'ilike', search.strip()))
        return self.env['account.batch.payment'].search(domain, order='date desc, id desc', limit=80)

    def _om_liquidity_lines_to_match(self, payment):
        return payment._seek_for_lines()[0].filtered(
            lambda line: not line.reconciled and line.account_id.reconcile and line.parent_state == 'posted')

    def _om_batch_amount(self, batch):
        """ What the bank still has to clear of the batch, positive, in the currency of the transaction. """
        self.ensure_one()
        trans_currency, _company_currency = self._om_currencies()
        total = 0.0
        for payment in batch._om_payments_to_match():
            if payment.move_id:
                total += sum(abs(self._om_to_transaction_amount(
                    line.currency_id, line.amount_residual_currency, line.amount_residual))
                    for line in self._om_liquidity_lines_to_match(payment))
            else:
                total += self._om_payment_to_transaction_amount(payment, payment.amount)
        return trans_currency.round(total)

    def _om_payment_to_transaction_amount(self, payment, amount):
        trans_currency, _company_currency = self._om_currencies()
        if payment.currency_id == trans_currency:
            return amount
        return payment.currency_id._convert(amount, trans_currency, self.company_id, self.date)

    def _om_batch_proposal(self, batches):
        """ Proposal clearing the payments of `batches` not cleared yet.

        A payment with a journal entry is matched by its outstanding line. A payment without one (no outstanding
        account on its payment method) is matched with the open items of the invoices it pays, up to its amount;
        what it pays beyond them goes to the receivable or payable account of the partner.

        :return: dictionary with matches and writeoffs (see `_om_reconcile`), each with the `payment_ids` it comes
                 from, and `batch_payment_ids`
        """
        self.ensure_one()
        matches = {}  # journal item: {'amount': part to reconcile or None for all, 'payment_ids': [...]}
        writeoffs = []
        payments = batches._om_payments_to_match()
        for payment in payments:
            if payment.move_id:
                for line in self._om_liquidity_lines_to_match(payment):
                    matches.setdefault(line, {'amount': None, 'payment_ids': []})['payment_ids'].append(payment.id)
                continue
            to_allocate = payment.amount
            direction = -1 if payment.payment_type == 'outbound' else 1
            open_lines = payment.invoice_ids.line_ids.filtered(
                lambda line: line.account_id.account_type in OPEN_ACCOUNT_TYPES and not line.reconciled
                and line.parent_state == 'posted' and line.amount_residual_currency * direction > 0
            ).sorted(lambda line: (line.date_maturity or line.date, line.id))
            for line in open_lines:
                if payment.currency_id.is_zero(to_allocate):
                    break
                entry = matches.setdefault(line, {'amount': 0.0, 'payment_ids': []})
                entry['payment_ids'].append(payment.id)
                if line.currency_id != payment.currency_id or entry['amount'] is None:
                    # an item in another currency is matched whole, at the rate of the bank
                    entry['amount'] = None
                    to_allocate = 0.0
                    break
                part = min(abs(line.amount_residual_currency) - entry['amount'], to_allocate)
                entry['amount'] += part
                to_allocate -= part
            if not payment.currency_id.is_zero(to_allocate):
                amount = self._om_payment_to_transaction_amount(payment, to_allocate)
                writeoffs.append({
                    'account_id': payment.destination_account_id.id,
                    'amount': -direction * amount,
                    'label': payment.name,
                    'partner_id': payment.partner_id.id,
                    'tax_ids': [],
                    'tax_included': False,
                    'analytic_distribution': False,
                    'reconcile_model_id': False,
                    'payment_ids': [payment.id],
                })
        for line, vals in matches.items():
            if vals['amount'] is not None and line.currency_id.compare_amounts(
                    vals['amount'], abs(line.amount_residual_currency)) == 0:
                # a whole item: the engine then caps it to what the transaction still covers
                vals['amount'] = None
        return {
            'matches': [{'aml_id': line.id, 'amount': vals['amount'], 'payment_ids': vals['payment_ids']}
                        for line, vals in matches.items()],
            'writeoffs': writeoffs,
            'batch_payment_ids': payments.ids,
        }

    def _om_scored_batches(self):
        """ :return: list of (batch, score) of the open batches the transaction may clear, best first """
        self.ensure_one()
        trans_currency, _company_currency = self._om_currencies()
        to_cover = abs(self.amount_residual)
        label = (self.payment_ref or '').upper().replace(' ', '')
        scored = []
        for batch in self._om_open_batches():
            score = 0
            if trans_currency.compare_amounts(self._om_batch_amount(batch), to_cover) == 0:
                score += SCORE_AMOUNT
            if batch.name.upper().replace(' ', '') in label:
                score += SCORE_REFERENCE
            if score:
                scored.append((batch, score))
        scored.sort(key=lambda item: -item[1])
        return scored

    def _om_best_batch(self):
        """ :return: (batch, score) of the one batch scoring best, or (None, 0) """
        scored = self._om_scored_batches()
        if not scored or (len(scored) > 1 and scored[0][1] == scored[1][1]):
            return None, 0
        return scored[0]

    # -------------------------------------------------------------------------
    # Engine
    # -------------------------------------------------------------------------

    def _om_suggested_proposal(self):
        proposal = super()._om_suggested_proposal()
        if proposal.get('score', 0) >= SCORE_PERFECT:
            return proposal
        batch, score = self._om_best_batch()
        # the reference of the batch in the label beats a matching amount; an amount alone only fills a gap
        if batch and (score >= SCORE_REFERENCE or not proposal):
            return {**self._om_batch_proposal(batch), 'score': score}
        return proposal

    def _om_clean_proposal(self, proposal):
        cleaned = super()._om_clean_proposal(proposal)
        payment_ids = (proposal or {}).get('batch_payment_ids') or []
        cleaned['batch_payment_ids'] = [int(payment_id) for payment_id in payment_ids]
        return cleaned

    def _om_requested_amount(self, proposal):
        """ What the proposal asks to reconcile, before the matches are capped to the transaction, positive, in
        the currency of the transaction. """
        total = 0.0
        for match in proposal.get('matches') or []:
            aml = self.env['account.move.line'].browse(match['aml_id'])
            residual = abs(self._om_to_transaction_amount(
                aml.currency_id, aml.amount_residual_currency, aml.amount_residual))
            if match.get('amount') is not None and aml.amount_residual_currency:
                residual *= abs(match['amount']) / abs(aml.amount_residual_currency)
            total += residual
        return total + sum(abs(writeoff.get('amount') or 0.0) for writeoff in proposal.get('writeoffs') or [])

    def _om_reconcile(self, proposal):
        payments = self.env['account.payment']
        covered = False
        if proposal.get('batch_payment_ids'):
            payments = self.env['account.payment'].browse(proposal['batch_payment_ids']).exists().filtered(
                'batch_payment_id')
            trans_currency, _company_currency = self._om_currencies()
            lines = self._om_prepare_proposal_lines(proposal)
            reconciled = sum(abs(self._om_to_transaction_amount(
                self.env['res.currency'].browse(vals['currency_id']), vals['amount_currency'], vals['balance']))
                for vals, _aml in lines)
            covered = trans_currency.compare_amounts(reconciled, self._om_requested_amount(proposal)) == 0
        res = super()._om_reconcile(proposal)
        if payments:
            self.om_batch_payment_ids |= payments
            moveless = payments.filtered(lambda payment: not payment.move_id and payment.state == 'in_process')
            if covered:
                # a payment without journal entry has nothing the bank can clear: it is paid with its invoices
                moveless.action_validate()
            elif moveless:
                for batch in moveless.batch_payment_id:
                    batch.message_post(body=_(
                        'The transaction %(transaction)s cleared part of the batch only: check the payments '
                        'paid and mark them as paid.', transaction=self.display_name))
        return res

    def action_undo_reconciliation(self):
        payments = self.om_batch_payment_ids
        res = super().action_undo_reconciliation()
        payments.filtered(lambda payment: not payment.move_id and payment.state == 'paid').write(
            {'state': 'in_process'})
        self.om_batch_payment_ids = False
        return res

    def _om_auto_reconcile_one(self, models):
        if super()._om_auto_reconcile_one(models):
            return True
        if self.is_reconciled or not self.company_id.om_reconcile_auto:
            return False
        batch, score = self._om_best_batch()
        if batch and score >= SCORE_PERFECT:
            proposal = self._om_batch_proposal(batch)
            if self._om_is_complete(proposal):
                self._om_reconcile(proposal)
                return True
        return False

    # -------------------------------------------------------------------------
    # Screen
    # -------------------------------------------------------------------------

    def _om_screen_batch_proposal(self, batches):
        proposal = self._om_batch_proposal(batches)
        AccountMoveLine = self.env['account.move.line']
        for match in proposal['matches']:
            match['candidate'] = self._om_screen_candidate(AccountMoveLine.browse(match['aml_id']))
        return proposal

    def om_bank_rec_get_data(self):
        data = super().om_bank_rec_get_data()
        if self.is_reconciled:
            return data
        batch, _score = self._om_best_batch()
        if batch:
            proposal = self._om_screen_batch_proposal(batch)
            suggested_ids = {match['aml_id'] for match in data['suggestion']['matches']}
            if suggested_ids == {match['aml_id'] for match in proposal['matches']} and (
                    suggested_ids or proposal['writeoffs']):
                data['suggestion'] = {**proposal, 'batch_name': batch.name}
        return data

    def om_bank_rec_batches(self, search=None):
        """ The open batches the transaction may clear, for the Batches tab of the screen. """
        self.ensure_one()
        self._om_check_access()
        trans_currency, _company_currency = self._om_currencies()
        scores = dict(self._om_scored_batches())
        result = []
        for batch in self._om_open_batches(search=search):
            result.append({
                'id': batch.id,
                'name': batch.name,
                'date_display': format_date(self.env, batch.date),
                'payment_count': len(batch._om_payments_to_match()),
                'amount': self._om_batch_amount(batch),
                'currency_id': trans_currency.id,
                'score': scores.get(batch, 0),
            })
        result.sort(key=lambda item: -item['score'])
        return result

    def om_bank_rec_batch_proposal(self, batch_id):
        self.ensure_one()
        self._om_check_access()
        batch = self.env['account.batch.payment'].browse(batch_id)
        if batch.journal_id != self.journal_id or batch.state != 'sent':
            return {'matches': [], 'writeoffs': [], 'batch_payment_ids': []}
        return self._om_screen_batch_proposal(batch)
