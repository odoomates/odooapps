from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

# what the screen offers to clear, in the order the accountants go through them
OPEN_ITEM_ACCOUNT_TYPES = {
    'receivable': 'asset_receivable',
    'payable': 'liability_payable',
}


class AccountMoveLine(models.Model):
    """ Data exchanged with the open items side of the reconciliation screen.

    Open items are the journal items of a customer or of a supplier that no payment has cleared yet: an
    invoice waiting for its payment, a payment waiting for its invoice, a credit note to deduct. They are
    reconciled against each other without any transaction of the bank, which is what a cash payment, a
    credit note or a settlement between two invoices needs.
    """
    _inherit = 'account.move.line'

    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------

    def _om_open_item(self):
        self.ensure_one()
        return {
            'id': self.id,
            'date_display': format_date(self.env, self.date),
            'date_maturity_display': format_date(self.env, self.date_maturity) if self.date_maturity else '',
            'move_id': self.move_id.id,
            'move_name': self.move_id.name,
            'label': ' - '.join(part for part in (self.move_id.ref, self.name)
                                if part and part != self.move_id.name) or '',
            'partner_id': self.partner_id.id,
            'partner_name': self.partner_id.display_name or '',
            'account_id': self.account_id.id,
            'account_display': self.account_id.display_name,
            'amount_residual': self.amount_residual,
            'amount_residual_currency': self.amount_residual_currency,
            'currency_id': self.currency_id.id,
            'company_currency_id': self.company_id.currency_id.id,
        }

    # -------------------------------------------------------------------------
    # Screen API
    # -------------------------------------------------------------------------

    @api.model
    def _om_open_items_domain(self, account_type=None, account_id=None, partner_id=None):
        domain = [
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('company_id', 'in', self.env.companies.ids),
            ('account_id.reconcile', '=', True),
            ('amount_residual', '!=', 0.0),
        ]
        if account_id:
            domain.append(('account_id', '=', account_id))
        elif account_type in OPEN_ITEM_ACCOUNT_TYPES:
            domain.append(('account_id.account_type', '=', OPEN_ITEM_ACCOUNT_TYPES[account_type]))
        else:
            domain.append(('account_id.account_type', 'in', list(OPEN_ITEM_ACCOUNT_TYPES.values())))
        if partner_id:
            domain.append(('partner_id', '=', partner_id))
        return domain

    @api.model
    def om_open_items_search_groups(self, account_type='receivable', search=None, limit=80, offset=0):
        """ The partners having journal items left to clear, with what they add up to.

        A group is a partner on an account: the items of one group are the ones that can be reconciled
        together, since reconciliation happens on a single account.
        """
        self.env['account.bank.statement.line']._om_check_access()
        domain = self._om_open_items_domain(account_type=account_type)
        if search:
            search = search.strip()
            text_domain = ['|', '|', ('partner_id.name', 'ilike', search), ('move_id.name', 'ilike', search),
                           ('name', 'ilike', search)]
            try:
                number = float(search.replace(',', ''))
                text_domain = ['|', '|', ('amount_residual', '=', number),
                               ('amount_residual', '=', -number)] + text_domain
            except ValueError:
                pass
            domain += text_domain
        rows = self._read_group(
            domain,
            groupby=['partner_id', 'account_id'],
            aggregates=['amount_residual:sum', '__count'],
            order='partner_id',
        )
        groups = []
        for partner, account, residual, count in rows:
            # a partner with items on one side only has nothing to clear against each other
            groups.append({
                'partner_id': partner.id,
                'partner_name': partner.display_name or _('No partner'),
                'account_id': account.id,
                'account_display': account.display_name,
                'residual': residual,
                'count': count,
                'currency_id': account.company_currency_id.id or self.env.company.currency_id.id,
            })
        groups.sort(key=lambda group: (-abs(group['residual']), group['partner_name']))
        return {'groups': groups[offset:offset + limit], 'count': len(groups)}

    @api.model
    def om_open_items_get_lines(self, partner_id, account_id):
        """ The journal items left to clear for one partner on one account, oldest first. """
        self.env['account.bank.statement.line']._om_check_access()
        domain = self._om_open_items_domain(account_id=account_id, partner_id=partner_id)
        lines = self.search(domain, order='date_maturity, date, id')
        debit = sum(line.amount_residual for line in lines if line.amount_residual > 0)
        credit = -sum(line.amount_residual for line in lines if line.amount_residual < 0)
        return {
            'lines': [line._om_open_item() for line in lines],
            'debit': debit,
            'credit': credit,
            'clearable': min(debit, credit),
            'suggestion': lines._om_open_items_suggestion(),
        }

    def _om_open_items_suggestion(self):
        """ :return: the ids of the oldest items of both sides whose amounts cancel each other exactly

        What an accountant does by hand: take the oldest invoice, take the payments that cover it, clear them.
        Nothing is proposed when no combination lands on zero, rather than proposing something that leaves a
        difference the user did not ask for.
        """
        currency = self.company_id[:1].currency_id or self.env.company.currency_id
        debits = sorted((line for line in self if line.amount_residual > 0),
                        key=lambda line: (line.date_maturity or line.date, line.id))
        credits = sorted((line for line in self if line.amount_residual < 0),
                         key=lambda line: (line.date_maturity or line.date, line.id))
        if not debits or not credits:
            return []
        # the oldest item of the smaller side, cleared with the oldest items of the other side
        for side, other in ((debits, credits), (credits, debits)):
            target = abs(side[0].amount_residual)
            total = 0.0
            picked = []
            for line in other:
                total += abs(line.amount_residual)
                picked.append(line)
                comparison = currency.compare_amounts(total, target)
                if comparison == 0:
                    return [side[0].id] + [line.id for line in picked]
                if comparison > 0:
                    break
        return []

    @api.model
    def om_open_items_reconcile(self, line_ids, writeoff=None):
        """ Reconcile the journal items the user picked.

        What is picked does not have to cancel out: a payment smaller than its invoice settles part of it and
        the rest stays open, which is what a partial payment is. The difference is only written off when the
        user asks for it. What cannot be done is reconciling items that are all on the same side, since
        nothing would settle anything.
        """
        lines = self.browse(line_ids).exists()
        if len(lines) < 2:
            raise UserError(_('Pick at least two journal items to reconcile them together.'))
        if not (any(line.amount_residual > 0 for line in lines)
                and any(line.amount_residual < 0 for line in lines)):
            raise UserError(_(
                'The journal items picked are all on the same side: pick what is owed together with what '
                'settles it, e.g. an invoice and its payment.'))
        lines._om_reconcile_items(writeoff=writeoff)
        return True
