from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import queries

FEE_TYPES = ('CHARGE', 'REFUND', 'ADJUSTMENT')


class OmShopifyPayout(models.Model):
    """ A payout of Shopify Payments: the money Shopify sent to the bank, with its charges,
    refunds and fees as bank statement lines of the payout journal. """
    _name = 'om.shopify.payout'
    _description = 'Shopify Payout'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    shopify_gid = fields.Char(string='Shopify ID', required=True, readonly=True)
    date = fields.Date(readonly=True)
    status = fields.Char(readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    amount = fields.Monetary(string='Net Amount', readonly=True)
    statement_line_ids = fields.One2many('account.bank.statement.line', 'shopify_payout_id', string='Statement Lines')
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    bank_line_id = fields.Many2one('account.bank.statement.line', string='Bank Transaction', readonly=True, copy=False,
                                   help="The transaction of the bank that received this payout, reconciled with it.")
    matched_count = fields.Integer(string='Matched Payments', readonly=True)
    unmatched_count = fields.Integer(string='Payments to Match', readonly=True,
                                     help="Charges and refunds of the payout with no payment found in Odoo: they stay "
                                          "open on the transit account.")
    fee_amount = fields.Monetary(string='Fees', readonly=True)
    gross_amount = fields.Monetary(string='Gross Amount', readonly=True)
    state = fields.Selection([('draft', 'To Import'), ('done', 'Imported'), ('failed', 'Failed (Reversed)')],
                             default='draft', readonly=True)

    _store_gid_unique = models.Constraint('unique (store_id, shopify_gid)', "A payout is imported once per store.")

    @api.model
    def _shopify_import(self, store):
        """ Import the paid payouts not imported yet, with their transactions. """
        if not store.payout_journal_id:
            raise UserError(_("Set the payout journal of %(store)s.", store=store.name))
        started = fields.Datetime.now()
        known = set(self.search([('store_id', '=', store.id)]).mapped('shopify_gid'))
        if store.payout_mode == 'entry':
            store._shopify_check_payout_setup()
        payouts = self.browse()
        for node in store._shopify_paginate(queries.PAYOUTS, {'query': 'status:paid'}, 'shopifyPaymentsAccount.payouts'):
            if node['id'] in known:
                continue
            currency = self.env['res.currency'].search([('name', '=', (node.get('net') or {}).get('currencyCode'))],
                                                       limit=1)
            payout = self.create({
                'name': _("Payout %(date)s", date=(node.get('issuedAt') or '')[:10]),
                'store_id': store.id,
                'shopify_gid': node['id'],
                'date': (node.get('issuedAt') or '')[:10] or fields.Date.today(),
                'status': node.get('status'),
                'currency_id': currency.id or store.company_id.currency_id.id,
                'amount': float((node.get('net') or {}).get('amount') or 0.0),
            })
            if store.payout_mode == 'entry':
                payout._shopify_post_entry()
            else:
                payout._shopify_import_transactions()
            payouts |= payout
        failed = self._shopify_reverse_failed(store)
        store.payout_last_sync = started
        return _("%(count)s payout(s) imported, %(failed)s reversed", count=len(payouts), failed=failed)

    @api.model
    def _shopify_reverse_failed(self, store):
        """ Reverse the entries of the payouts that failed after their import (the bank refused them). """
        imported = {p.shopify_gid: p for p in self.search([('store_id', '=', store.id), ('state', '=', 'done')])}
        if not imported:
            return 0
        count = 0
        for node in store._shopify_paginate(queries.PAYOUTS, {'query': 'status:failed'}, 'shopifyPaymentsAccount.payouts'):
            payout = imported.get(node['id'])
            if not payout:
                continue
            if payout.move_id.state == 'posted':
                payout.move_id._reverse_moves([{'ref': _("Failed %(payout)s", payout=payout.name),
                                                'date': fields.Date.context_today(self)}], cancel=True)
            payout.write({'state': 'failed', 'status': node.get('status')})
            payout.message_post(body=_("This payout failed in Shopify: its entry was reversed."))
            count += 1
        return count

    def _shopify_transactions(self):
        self.ensure_one()
        payout_id = self.shopify_gid.rsplit('/', 1)[-1]
        return [node for node in self.store_id._shopify_paginate(
            queries.BALANCE_TRANSACTIONS, {'query': f'payout_id:{payout_id}'}, 'shopifyPaymentsAccount.balanceTransactions')
            if node.get('type') != 'PAYOUT']

    def _shopify_order(self, node):
        gid = (node.get('associatedOrder') or {}).get('id')
        if not gid:
            return self.env['sale.order']
        return self.env['sale.order'].search([('shopify_store_id', '=', self.store_id.id),
                                              ('shopify_order_gid', '=', gid)], limit=1)

    def _shopify_post_entry(self):
        """ One journal entry for the payout: each charge and refund on the transit account (where the
        payments of Shopify Payments wait), the fees and the adjustments on their accounts, and the net
        amount on the internal transfer account, that the bank transaction clears. Then match the
        payments of the orders and the bank transaction. """
        self.ensure_one()
        store = self.store_id
        currency = self.currency_id
        lines, fees, gross = [], 0.0, 0.0
        for node in self._shopify_transactions():
            amount = float((node.get('amount') or {}).get('amount') or 0.0)
            fees += float((node.get('fee') or {}).get('amount') or 0.0)
            order = self._shopify_order(node)
            kind = node.get('type') or ''
            label = ' '.join(filter(None, [kind.replace('_', ' ').capitalize(),
                                           (node.get('associatedOrder') or {}).get('name')]))
            account = store.payout_transit_account_id if kind in ('CHARGE', 'REFUND') \
                else store.payout_adjustment_account_id
            if kind == 'CHARGE':
                gross += amount
            lines.append({
                'name': label, 'account_id': account.id, 'balance': -amount,
                'partner_id': order.partner_invoice_id.commercial_partner_id.id or False,
                'om_shopify_order_id': order.id,
            })
        if fees:
            lines.append({'name': _("Shopify Payments fees"), 'account_id': store.payout_fee_account_id.id,
                          'balance': fees})
        net = currency.round(sum(-l['balance'] for l in lines))
        difference = currency.round(self.amount - net)
        if not currency.is_zero(difference):
            lines.append({'name': _("Difference with the payout"), 'account_id': store.payout_adjustment_account_id.id,
                          'balance': -difference})
        lines.append({'name': self.name, 'account_id': store.payout_clearing_account_id.id, 'balance': self.amount})
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': store.payout_entry_journal_id.id,
            'date': self.date,
            'ref': _("Shopify %(payout)s", payout=self.name),
            'line_ids': [fields.Command.create({k: v for k, v in l.items() if k != 'om_shopify_order_id'})
                         for l in lines],
        })
        move.action_post()
        matched, unmatched = self._shopify_match_payments(move, lines)
        self.write({'move_id': move.id, 'state': 'done', 'matched_count': matched, 'unmatched_count': unmatched,
                    'fee_amount': fees, 'gross_amount': gross})
        self._shopify_match_bank()
        return move

    def _shopify_match_payments(self, move, lines):
        """ Reconcile each charge or refund of the payout with the payment of its order on the transit
        account, when there is one of the same amount. Gives ``(matched, unmatched)``. """
        transit = self.store_id.payout_transit_account_id
        AML = self.env['account.move.line']
        matched = unmatched = 0
        payout_lines = move.line_ids.filtered(lambda l: l.account_id == transit)
        for payout_line in payout_lines:
            domain = [('account_id', '=', transit.id), ('reconciled', '=', False), ('parent_state', '=', 'posted'),
                      ('move_id', '!=', move.id), ('company_id', '=', move.company_id.id)]
            if payout_line.partner_id:
                domain.append(('partner_id', 'child_of', payout_line.partner_id.id))
            # the payment is on the other side of the transit account, for the same amount
            domain.append(('balance', '=', -payout_line.balance))
            candidate = AML.search(domain, order='date desc, id desc', limit=1)
            if candidate:
                (payout_line | candidate).reconcile()
                matched += 1
            else:
                unmatched += 1
        return matched, unmatched

    def _shopify_match_bank(self):
        """ Reconcile the bank transaction of the payout, when exactly one fits: same amount, a few days
        after the payout, not reconciled yet. """
        self.ensure_one()
        store = self.store_id
        if not store.payout_journal_id or not self.move_id:
            return False
        clearing_line = self.move_id.line_ids.filtered(
            lambda l: l.account_id == store.payout_clearing_account_id and not l.reconciled)
        candidates = self.env['account.bank.statement.line'].search([
            ('journal_id', '=', store.payout_journal_id.id), ('is_reconciled', '=', False),
            ('amount', '=', self.amount),
            ('date', '>=', self.date - timedelta(days=3)), ('date', '<=', self.date + timedelta(days=10)),
            ('shopify_payout_id', '=', False),
        ])
        if len(candidates) != 1 or not clearing_line:
            return False
        st_line = candidates
        _liquidity, suspense, _other = st_line._seek_for_lines()
        AML = self.env['account.move.line'].with_context(skip_readonly_check=True, check_move_validity=False)
        counterpart = AML.create({
            'move_id': st_line.move_id.id, 'name': self.name, 'account_id': store.payout_clearing_account_id.id,
            'balance': -self.amount, 'partner_id': False,
        })
        suspense.with_context(force_delete=True, skip_readonly_check=True, check_move_validity=False).unlink()
        (counterpart | clearing_line).reconcile()
        st_line.shopify_payout_id = self
        self.bank_line_id = st_line
        return True

    def action_match_bank(self):
        for payout in self.filtered(lambda p: p.state == 'done' and not p.bank_line_id):
            if not payout._shopify_match_bank():
                raise UserError(_("No single bank transaction of %(amount)s around %(date)s in %(journal)s.",
                                  amount=payout.currency_id.format(payout.amount), date=payout.date,
                                  journal=payout.store_id.payout_journal_id.display_name))

    def action_open_move(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'account.move', 'res_id': self.move_id.id,
                'view_mode': 'form'}

    def _shopify_import_transactions(self):
        """ One statement line per order charge or refund, with its customer, and one line for all the
        fees; Odoo matches them with the invoices and payments in the bank reconciliation. """
        self.ensure_one()
        store = self.store_id
        StatementLine = self.env['account.bank.statement.line']
        payout_id = self.shopify_gid.rsplit('/', 1)[-1]
        fees = 0.0
        lines = []
        for node in store._shopify_paginate(queries.BALANCE_TRANSACTIONS, {'query': f'payout_id:{payout_id}'},
                                            'shopifyPaymentsAccount.balanceTransactions'):
            if node.get('type') == 'PAYOUT':
                continue
            amount = float((node.get('amount') or {}).get('amount') or 0.0)
            fees += float((node.get('fee') or {}).get('amount') or 0.0)
            order = self.env['sale.order']
            if gid := (node.get('associatedOrder') or {}).get('id'):
                order = self.env['sale.order'].search([('shopify_store_id', '=', store.id),
                                                       ('shopify_order_gid', '=', gid)], limit=1)
            lines.append({
                'journal_id': store.payout_journal_id.id,
                'date': (node.get('transactionDate') or '')[:10] or self.date,
                'amount': amount,
                'payment_ref': ' '.join(filter(None, [
                    node.get('type', '').replace('_', ' ').capitalize(),
                    (node.get('associatedOrder') or {}).get('name'),
                    order.invoice_ids.filtered(lambda m: m.state == 'posted')[:1].name,
                ])),
                'partner_id': order.partner_id.commercial_partner_id.id or False,
                'shopify_payout_id': self.id,
            })
        if fees:
            lines.append({
                'journal_id': store.payout_journal_id.id,
                'date': self.date,
                'amount': -fees,
                'payment_ref': _("Shopify Payments fees"),
                'shopify_payout_id': self.id,
            })
        StatementLine.create(lines)
        self.state = 'done'


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    shopify_payout_id = fields.Many2one('om.shopify.payout', string='Shopify Payout', readonly=True,
                                        index='btree_not_null', ondelete='set null')
