from odoo import api, fields, models, Command, _
from odoo.exceptions import LockError, UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def _om_check_matchable(self):
        self.env['account.bank.statement.line']._om_check_access()
        if len(self) < 1:
            raise UserError(_('Select the journal items to match.'))
        if len(self.account_id) != 1:
            raise UserError(_('The journal items to match must use the same account.'))
        if len(self.company_id.root_id) != 1:
            raise UserError(_('The journal items to match must belong to the same company.'))
        account = self.account_id
        if not account.reconcile and account.account_type not in ('asset_cash', 'liability_credit_card'):
            raise UserError(_('The account %s does not allow reconciliation.', account.display_name))
        for line in self:
            if line.parent_state != 'posted':
                raise UserError(_('The journal entry %s must be posted before being reconciled.',
                                  line.move_id.display_name))
            if line.reconciled:
                raise UserError(_('The journal item %s is already reconciled.', line.display_name))

    def _om_matching_summary(self):
        """ Amounts of the selected journal items.

        :return: dictionary with the residual debit, credit and difference in company currency, and in the foreign
                 currency when all the items share it.
        """
        company_currency = self.company_id.root_id.currency_id[:1] or self.env.company.currency_id
        debit = sum(line.amount_residual for line in self if line.amount_residual > 0)
        credit = -sum(line.amount_residual for line in self if line.amount_residual < 0)
        currencies = self.currency_id
        summary = {
            'company_currency_id': company_currency.id,
            'debit': company_currency.round(debit),
            'credit': company_currency.round(credit),
            'difference': company_currency.round(debit - credit),
            'currency_id': False,
            'difference_currency': 0.0,
            'partner_ids': self.partner_id.ids,
            'account_id': self.account_id[:1].id,
        }
        if len(currencies) == 1 and currencies != company_currency:
            summary.update({
                'currency_id': currencies.id,
                'difference_currency': currencies.round(sum(self.mapped('amount_residual_currency'))),
            })
        return summary

    def _om_reconcile_items(self, writeoff=None):
        """ Reconcile the selected journal items together; the difference is written off when `writeoff` is given.

        :param writeoff: dictionary with account_id, journal_id, date, label
        """
        self._om_check_matchable()
        try:
            self.lock_for_update()
        except LockError:
            raise UserError(
                _('These journal items are being reconciled by someone else, please try again in a moment.'))
        summary = self._om_matching_summary()
        company_currency = self.env['res.currency'].browse(summary['company_currency_id'])
        lines = self
        needs_writeoff = not company_currency.is_zero(summary['difference']) or (
            summary['currency_id']
            and not self.env['res.currency'].browse(summary['currency_id']).is_zero(summary['difference_currency']))
        if writeoff and needs_writeoff:
            lines |= self._om_create_writeoff(summary, writeoff)
        self._reconcile_plan([lines])
        return True

    def _om_create_writeoff(self, summary, writeoff):
        partner = self.partner_id if len(self.partner_id) == 1 else self.env['res.partner']
        account = self.account_id
        company = self.company_id.root_id if self.company_id.root_id in self.env.companies else self.company_id[:1]
        journal = self.env['account.journal'].browse(writeoff['journal_id'])
        currency = (self.env['res.currency'].browse(summary['currency_id'])
                    if summary['currency_id'] else company.currency_id)
        difference = summary['difference']
        difference_currency = summary['difference_currency'] if summary['currency_id'] else difference
        label = writeoff.get('label') or _('Write-off')
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'company_id': journal.company_id.id,
            'date': writeoff.get('date') or fields.Date.context_today(self),
            'ref': label,
            'line_ids': [
                Command.create({
                    'name': label,
                    'account_id': account.id,
                    'partner_id': partner.id,
                    'currency_id': currency.id,
                    'amount_currency': -difference_currency,
                    'balance': -difference,
                }),
                Command.create({
                    'name': label,
                    'account_id': writeoff['account_id'],
                    'partner_id': partner.id,
                    'currency_id': currency.id,
                    'amount_currency': difference_currency,
                    'balance': difference,
                }),
            ],
        })
        move.action_post()
        return move.line_ids.filtered(lambda line: line.account_id == account)

    @api.model
    def _om_suggest_item_matches(self, domain=None, limit=50):
        """ Groups of open journal items of a same account and partner whose residual amounts cancel each other.

        :return: list of journal item recordsets
        """
        domain = list(domain or []) + [
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('account_id.reconcile', '=', True),
            ('company_id', 'in', self.env.companies.ids),
        ]
        groups = self._read_group(domain, groupby=['account_id', 'partner_id'],
                                  aggregates=['amount_residual:sum', 'id:recordset'],
                                  having=[('__count', '>', 1)], limit=limit * 4)
        suggestions = []
        for _account, _partner, residual_sum, lines in groups:
            currency = lines.company_id.root_id.currency_id[:1] or self.env.company.currency_id
            debits = lines.filtered(lambda line: line.amount_residual > 0)
            credits = lines.filtered(lambda line: line.amount_residual < 0)
            if not debits or not credits:
                continue
            if currency.is_zero(residual_sum):
                suggestions.append(lines)
            else:
                # pairs of items with opposite amounts
                used = self.browse()
                for debit in debits.sorted(lambda line: (line.date, line.id)):
                    credit = (credits - used).filtered(
                        lambda line: currency.compare_amounts(-line.amount_residual, debit.amount_residual) == 0)[:1]
                    if credit:
                        used |= credit
                        suggestions.append(debit | credit)
            if len(suggestions) >= limit:
                break
        return suggestions[:limit]

    def om_action_match(self):
        """ Open the wizard matching the selected journal items. """
        self._om_check_matchable()
        return {
            'name': _('Match Journal Items'),
            'type': 'ir.actions.act_window',
            'res_model': 'om.reconcile.items.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': 'account.move.line', 'active_ids': self.ids},
        }

    @api.model
    def om_action_match_suggestions(self, domain=None):
        """ Reconcile the groups of open items of a same account and partner cancelling each other. """
        self.env['account.bank.statement.line']._om_check_access()
        count = 0
        for lines in self._om_suggest_item_matches(domain or []):
            lines._om_reconcile_items()
            count += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if count else 'info',
                'message': _('%s group(s) of journal items matched.', count) if count
                           else _('No journal items to match.'),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
