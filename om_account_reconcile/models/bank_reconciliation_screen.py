from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date


class AccountBankStatementLine(models.Model):
    """ Data exchanged with the bank reconciliation screen. Every method returns plain JSON-able values. """
    _inherit = 'account.bank.statement.line'

    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------

    def _om_screen_transaction(self):
        self.ensure_one()
        trans_currency, _company_currency = self._om_currencies()
        trans_amount = self.amount_currency if self.foreign_currency_id else self.amount
        return {
            'id': self.id,
            'date': fields.Date.to_string(self.date),
            'date_display': format_date(self.env, self.date),
            'label': self.payment_ref or '',
            'partner_id': self.partner_id.id,
            'partner_name': self.partner_id.display_name or self.partner_name or '',
            'amount': trans_amount,
            'currency_id': trans_currency.id,
            'journal_id': self.journal_id.id,
            'journal_name': self.journal_id.display_name,
            'is_reconciled': self.is_reconciled,
            # what the counterparts still have to cover, as a journal item amount
            'remaining': -self.amount_residual if not self.is_reconciled else 0.0,
            'review_state': self.move_id.review_state,
            'move_id': self.move_id.id,
        }

    def _om_screen_candidate(self, aml, score=None):
        self.ensure_one()
        trans_currency, _company_currency = self._om_currencies()
        return {
            'id': aml.id,
            'move_id': aml.move_id.id,
            'move_name': aml.move_id.name,
            'date_display': format_date(self.env, aml.date),
            'date_maturity_display': format_date(self.env, aml.date_maturity) if aml.date_maturity else '',
            'partner_name': aml.partner_id.display_name or '',
            'account_display': aml.account_id.display_name,
            'label': ' - '.join(part for part in (aml.move_id.ref, aml.name) if part and part != aml.move_id.name) or '',
            'residual_currency': aml.amount_residual_currency,
            'currency_id': aml.currency_id.id,
            'residual_transaction': trans_currency.round(self._om_to_transaction_amount(
                aml.currency_id, aml.amount_residual_currency, aml.amount_residual)),
            'score': score or 0,
        }

    def _om_screen_entry_lines(self):
        self.ensure_one()
        _liquidity_lines, suspense_lines, other_lines = self._seek_for_lines()
        lines = []
        for line in other_lines + suspense_lines:
            matched = line._all_reconciled_lines() - line
            lines.append({
                'id': line.id,
                'account_display': line.account_id.display_name,
                'partner_name': line.partner_id.display_name or '',
                'label': line.name or '',
                'amount_currency': line.amount_currency,
                'currency_id': line.currency_id.id,
                'balance': line.balance,
                'is_suspense': line in suspense_lines,
                'matched_move_names': matched.move_id.mapped('name'),
            })
        return lines

    # -------------------------------------------------------------------------
    # Screen API
    # -------------------------------------------------------------------------

    @api.model
    def om_bank_rec_search_transactions(self, journal_id=None, search=None, state='to_reconcile', limit=80, offset=0):
        self._om_check_access()
        domain = [('company_id', 'in', self.env.companies.ids)]
        if journal_id:
            domain.append(('journal_id', '=', journal_id))
        if state == 'to_reconcile':
            domain.append(('is_reconciled', '=', False))
        elif state == 'reconciled':
            domain.append(('is_reconciled', '=', True))
        if search:
            search = search.strip()
            text_domain = ['|', '|', ('payment_ref', 'ilike', search), ('partner_id.name', 'ilike', search),
                           ('partner_name', 'ilike', search)]
            try:
                number = float(search.replace(',', ''))
                text_domain = ['|', '|', ('amount', '=', number), ('amount', '=', -number)] + text_domain
            except ValueError:
                pass
            domain += text_domain
        st_lines = self.search(domain, order='date desc, id desc', limit=limit, offset=offset)
        return {
            'transactions': [st_line._om_screen_transaction() for st_line in st_lines],
            'count': self.search_count(domain),
        }

    def om_bank_rec_get_data(self):
        """ Everything the screen shows for one transaction. """
        self.ensure_one()
        self._om_check_access()
        data = {
            'transaction': self._om_screen_transaction(),
            'entry_lines': self._om_screen_entry_lines(),
            'suggestion': {'matches': []},
            'models': [],
        }
        if self.is_reconciled:
            return data
        suggestion = self._om_suggested_proposal()
        amls = self.env['account.move.line'].browse([match['aml_id'] for match in suggestion.get('matches', [])])
        data['suggestion'] = {
            'matches': [{'aml_id': aml.id, 'amount': None, 'candidate': self._om_screen_candidate(aml)} for aml in amls],
        }
        models = self.env['account.reconcile.model'].search([
            ('company_id', '=', self.company_id.id),
            ('rule_type', '=', 'reco_model'),
            ('mapped_partner_id', '=', False),
        ])
        data['models'] = [
            {'id': model.id, 'name': model.name, 'applicable': model._om_is_applicable(self)}
            for model in models if not model.match_journal_ids or self.journal_id in model.match_journal_ids
        ]
        return data

    def om_bank_rec_candidates(self, search=None, limit=40, offset=0):
        self.ensure_one()
        self._om_check_access()
        if search:
            amls = self._om_search_candidates(search=search, limit=limit, offset=offset)
            return [self._om_screen_candidate(aml) for aml in amls]
        scored = dict(self._om_scored_candidates(limit=limit))
        amls = list(scored)
        if len(amls) < limit:
            amls += list(self._om_search_candidates(limit=limit - len(amls)).filtered(lambda aml: aml not in scored))
        return [self._om_screen_candidate(aml, scored.get(aml)) for aml in amls]

    def om_bank_rec_preview(self, proposal):
        """ Journal items the proposal would create and what would be left, without writing anything. """
        self.ensure_one()
        self._om_check_access()
        proposal = self._om_clean_proposal(proposal)
        lines = self._om_prepare_proposal_lines(proposal)
        remaining_trans, remaining_balance = self._om_remaining(lines)
        trans_currency, company_currency = self._om_currencies()
        preview_lines = []
        for vals, aml in lines:
            currency = self.env['res.currency'].browse(vals['currency_id'])
            preview_lines.append({
                'kind': 'match' if aml else ('tax' if vals.get('tax_repartition_line_id') else 'writeoff'),
                'aml_id': aml.id,
                'account_display': self.env['account.account'].browse(vals['account_id']).display_name,
                'label': vals.get('name') or '',
                'amount_currency': vals['amount_currency'],
                'currency_id': currency.id,
                'amount_transaction': trans_currency.round(
                    self._om_to_transaction_amount(currency, vals['amount_currency'], vals['balance'])),
            })
        return {
            'lines': preview_lines,
            'remaining': remaining_trans,
            'is_complete': trans_currency.is_zero(remaining_trans) and company_currency.is_zero(remaining_balance),
        }

    def om_bank_rec_validate(self, proposal):
        self.ensure_one()
        self._om_reconcile(self._om_clean_proposal(proposal))
        return self.om_bank_rec_get_data()

    def om_bank_rec_undo(self):
        self.ensure_one()
        self._om_undo()
        return self.om_bank_rec_get_data()

    def om_bank_rec_model_writeoffs(self, model_id, proposal):
        """ Counterparts added by a reconciliation model on what the proposal leaves uncovered. """
        self.ensure_one()
        self._om_check_access()
        model = self.env['account.reconcile.model'].browse(model_id)
        if model.company_id != self.company_id:
            raise UserError(_('This reconciliation model belongs to another company.'))
        lines = self._om_prepare_proposal_lines(self._om_clean_proposal(proposal))
        remaining_trans, _remaining_balance = self._om_remaining(lines)
        return model._om_get_writeoffs(self, residual=remaining_trans)

    @api.model
    def om_bank_rec_auto_reconcile(self, st_line_ids):
        st_lines = self.browse(st_line_ids).filtered(lambda st_line: not st_line.is_reconciled)
        st_lines._om_check_access()
        return len(st_lines._om_auto_reconcile())

    def om_bank_rec_set_review(self, to_check):
        self.ensure_one()
        self._om_check_access()
        self.move_id.review_state = 'todo' if to_check else 'reviewed'
        return self.om_bank_rec_get_data()

    def _om_clean_proposal(self, proposal):
        """ Keep only the values the engine expects from what the screen sends. """
        proposal = proposal or {}
        return {
            'partner_id': proposal.get('partner_id') or False,
            'matches': [
                {'aml_id': int(match['aml_id']), 'amount': match.get('amount')}
                for match in proposal.get('matches') or []
            ],
            'writeoffs': [
                {
                    'account_id': int(writeoff['account_id']),
                    'amount': float(writeoff.get('amount') or 0.0),
                    'label': writeoff.get('label') or '',
                    'partner_id': writeoff.get('partner_id') or False,
                    'tax_ids': [int(tax_id) for tax_id in writeoff.get('tax_ids') or []],
                    'tax_included': bool(writeoff.get('tax_included')),
                    'analytic_distribution': writeoff.get('analytic_distribution') or False,
                    'reconcile_model_id': writeoff.get('reconcile_model_id') or False,
                }
                for writeoff in proposal.get('writeoffs') or [] if writeoff.get('account_id')
            ],
        }


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def om_action_open_bank_reconciliation(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'om_bank_reconciliation',
            'name': _('Bank Reconciliation'),
            'params': {'journal_id': self.id},
        }
