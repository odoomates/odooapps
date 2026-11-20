from odoo import fields, models, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _compute_payments_widget_to_reconcile_info(self):
        """ The transactions of the bank not reconciled yet are offered too: a customer paying an invoice shows up
        on it as soon as the statement is imported, and can be matched from the invoice. """
        super()._compute_payments_widget_to_reconcile_info()
        for move in self:
            if move.state != 'posted' or move.payment_state not in ('not_paid', 'partial') \
                    or not move.is_invoice(include_receipts=True):
                continue
            content = [
                {
                    'move_name': st_line.move_id.name,
                    'amount': amount,
                    'currency_id': move.currency_id.id,
                    'id': suspense_line.id,
                    'move_id': st_line.move_id.id,
                    'date': fields.Date.to_string(st_line.date),
                    'account_payment_id': False,
                    'ref': st_line.payment_ref or '',
                }
                for st_line, suspense_line, amount in move._om_outstanding_bank_lines()
            ]
            if not content:
                continue
            widget = move.invoice_outstanding_credits_debits_widget or {
                'outstanding': True,
                'content': [],
                'move_id': move.id,
                'title': _('Outstanding credits') if move.is_inbound() else _('Outstanding debits'),
            }
            move.invoice_outstanding_credits_debits_widget = {**widget, 'content': widget['content'] + content}

    def _om_outstanding_bank_lines(self):
        """ :return: list of (transaction, its suspense journal item, open amount in the currency of the invoice) of
        the transactions of the partner not reconciled yet, going the way of a payment of the invoice """
        self.ensure_one()
        st_lines = self.env['account.bank.statement.line'].search([
            ('partner_id', 'child_of', self.commercial_partner_id.id),
            ('is_reconciled', '=', False),
            ('company_id', 'child_of', self.company_id.root_id.id),
            ('amount', '>' if self.is_inbound() else '<', 0.0),
            ('state', '=', 'posted'),
        ], order='date, id', limit=20)
        result = []
        for st_line in st_lines:
            _liquidity_lines, suspense_lines, _other_lines = st_line._seek_for_lines()
            suspense_line = suspense_lines[:1]
            if not suspense_line:
                continue
            if suspense_line.currency_id == self.currency_id:
                amount = abs(suspense_line.amount_currency)
            else:
                amount = suspense_line.company_currency_id._convert(
                    abs(suspense_line.balance), self.currency_id, self.company_id, st_line.date)
            if not self.currency_id.is_zero(amount):
                result.append((st_line, suspense_line, amount))
        return result

    def js_assign_outstanding_line(self, line_id):
        """ A transaction of the bank picked in the outstanding widget is reconciled with the invoice by the bank
        reconciliation, as if the invoice was matched on the transaction. """
        self.ensure_one()
        line = self.env['account.move.line'].browse(line_id)
        st_line = line.move_id.statement_line_id
        if not st_line or line.account_id != st_line.journal_id.suspense_account_id:
            return super().js_assign_outstanding_line(line_id)
        if st_line.is_reconciled:
            raise UserError(_('The transaction %s is already reconciled.', st_line.display_name))
        term_lines = self.line_ids.filtered(
            lambda aml: aml.display_type == 'payment_term' and not aml.reconciled)
        if not term_lines:
            raise UserError(_('Nothing is left to pay on %s.', self.display_name))
        st_line._om_reconcile({
            'partner_id': st_line.partner_id.id or self.commercial_partner_id.id,
            'matches': [{'aml_id': aml.id} for aml in term_lines.sorted(lambda aml: (aml.date_maturity, aml.id))],
        })
        return True
