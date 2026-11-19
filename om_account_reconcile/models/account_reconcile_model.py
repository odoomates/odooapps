import re

from odoo import api, fields, models, Command, _

# the number of times a transaction is booked by hand on the same account before a rule is proposed for it
LEARN_AFTER = 3


class AccountReconcileModel(models.Model):
    _inherit = 'account.reconcile.model'

    om_auto_created = fields.Boolean(
        string='Learned', readonly=True, copy=False,
        help='Created from transactions booked by hand on the same account; review it and change it as you wish.')
    om_use_count = fields.Integer(string='Times Used', readonly=True, copy=False)
    om_bank_fee_journal_id = fields.Many2one(
        'account.journal', string='Bank Fees of', readonly=True, copy=False, index='btree_not_null',
        help='Technical: the bank journal this "Bank Fees" model was created for.')

    @api.model_create_multi
    def create(self, vals_list):
        models = super().create(vals_list)
        models._om_reapply_to_open_transactions()
        return models

    def write(self, vals):
        result = super().write(vals)
        if set(vals) - {'om_use_count', 'sequence', 'name'}:
            self._om_reapply_to_open_transactions()
        return result

    def _om_reapply_to_open_transactions(self):
        """ A new or changed automatic model is tried again on the transactions not reconciled yet. """
        automatic = self.filtered(lambda model: model.active and (
            model.trigger == 'auto_reconcile' or model.mapped_partner_id))
        if not automatic:
            return
        st_lines = self.env['account.bank.statement.line'].search([
            ('company_id', 'in', automatic.company_id.ids),
            ('is_reconciled', '=', False),
            ('om_auto_processed', '=', True),
        ])
        if st_lines:
            st_lines.om_auto_processed = False
            cron = self.env.ref('om_account_reconcile.ir_cron_auto_reconcile', raise_if_not_found=False)
            if cron:
                cron._trigger()

    # -------------------------------------------------------------------------
    # Bank fees
    # -------------------------------------------------------------------------

    @api.model
    def _om_sync_bank_fee_models(self, companies):
        """ One "Bank Fees" model per bank journal of the companies with a bank fees account; archived when the
        account is removed. """
        for company in companies:
            existing = self.with_context(active_test=False).search([
                ('company_id', '=', company.id), ('om_bank_fee_journal_id', '!=', False)])
            account = company.om_bank_fee_account_id
            if not account:
                existing.filtered('active').active = False
                continue
            journals = self.env['account.journal'].search([('company_id', '=', company.id), ('type', '=', 'bank')])
            for journal in journals:
                model = existing.filtered(lambda model: model.om_bank_fee_journal_id == journal)[:1]
                if model:
                    model.write({'active': True})
                    model.line_ids[:1].account_id = account
                    continue
                self.create({
                    'name': _('Bank Fees (%s)', journal.name),
                    'company_id': company.id,
                    'rule_type': 'reco_model',
                    'trigger': 'manual',
                    'om_bank_fee_journal_id': journal.id,
                    'match_journal_ids': [Command.set(journal.ids)],
                    'line_ids': [Command.create({
                        'account_id': account.id,
                        'label': _('Bank fees'),
                        'amount_type': 'percentage',
                        'amount_string': '100',
                    })],
                })

    # -------------------------------------------------------------------------
    # Learning from the transactions booked by hand
    # -------------------------------------------------------------------------

    @api.model
    def _om_label_keyword(self, label):
        """ The first word of a label worth matching on: letters only, at least 3 of them, e.g. STRIPE for
        "STRIPE PAYOUT 12/03". """
        for word in re.findall(r'[^\W\d_]+', label or ''):
            if len(word) >= 3:
                return word.upper()
        return False

    @api.model
    def _om_learn_from(self, st_line, writeoff):
        """ Propose a rule once transactions of the same partner, or with the same first word in their label, were
        booked by hand on the same account `LEARN_AFTER` times in the journal.

        :param writeoff: the counterpart typed by hand (see `_om_prepare_writeoff_lines_vals`)
        :return: the model created, or an empty recordset
        """
        account = self.env['account.account'].browse(writeoff['account_id'])
        partner = st_line.partner_id.commercial_partner_id
        keyword = False if partner else self._om_label_keyword(st_line.payment_ref)
        if not partner and not keyword:
            return self.browse()
        domain = [
            ('company_id', '=', st_line.company_id.id),
            ('statement_line_id.journal_id', '=', st_line.journal_id.id),
            ('account_id', '=', account.id),
            ('reconcile_model_id', '=', False),
            ('move_id', '!=', st_line.move_id.id),
        ]
        if partner:
            domain.append(('partner_id', 'child_of', partner.id))
        else:
            domain += [('partner_id', '=', False), ('statement_line_id.payment_ref', 'ilike', keyword)]
        earlier = self.env['account.move.line'].search(domain).move_id
        if len(earlier) + 1 < LEARN_AFTER:
            return self.browse()
        existing = self.with_context(active_test=False).search([
            ('company_id', '=', st_line.company_id.id),
            ('line_ids.account_id', '=', account.id),
        ]).filtered(lambda model: (partner and partner in model.match_partner_ids)
                    or (keyword and (model.match_label_param or '').upper() == keyword))
        if existing:
            return self.browse()
        return self.create({
            'name': _('%(who)s on %(account)s', who=partner.name or keyword, account=account.code or account.name),
            'company_id': st_line.company_id.id,
            'rule_type': 'reco_model',
            'trigger': 'manual',
            'om_auto_created': True,
            'match_journal_ids': [Command.set(st_line.journal_id.ids)],
            'match_partner_ids': [Command.set(partner.ids)] if partner else [],
            'match_label': False if partner else 'contains',
            'match_label_param': False if partner else keyword,
            'line_ids': [Command.create({
                'account_id': account.id,
                'amount_type': 'percentage',
                'amount_string': '100',
                'tax_ids': [Command.set(writeoff.get('tax_ids') or [])],
                'analytic_distribution': writeoff.get('analytic_distribution') or False,
            })],
        })

    def _om_label_texts(self, st_line):
        texts = [st_line.payment_ref or '']
        if st_line.transaction_details:
            texts.append(str(st_line.transaction_details))
        if st_line.narration:
            texts.append(str(st_line.narration))
        return texts

    def _om_is_applicable(self, st_line, partner=None):
        """ Whether the conditions of the model are fulfilled by the transaction.

        :param partner: partner the transaction is evaluated for, e.g. the one chosen in the reconciliation
                        screen and not saved yet (an empty recordset for none); its partner by default.
        """
        self.ensure_one()
        if partner is None:
            partner = st_line.partner_id
        if self.company_id != st_line.company_id:
            return False
        if self.match_journal_ids and st_line.journal_id not in self.match_journal_ids:
            return False
        amount = abs(st_line.amount)
        if self.match_amount == 'lower' and amount > self.match_amount_max:
            return False
        if self.match_amount == 'greater' and amount < self.match_amount_min:
            return False
        if self.match_amount == 'between' and not self.match_amount_min <= amount <= self.match_amount_max:
            return False
        if self.match_label and self.match_label_param:
            texts = self._om_label_texts(st_line)
            if self.match_label == 'contains':
                if not any(self.match_label_param.lower() in text.lower() for text in texts):
                    return False
            elif self.match_label == 'not_contains':
                if any(self.match_label_param.lower() in text.lower() for text in texts):
                    return False
            elif self.match_label == 'match_regex':
                if not any(re.search(self.match_label_param, text) for text in texts):
                    return False
        if (self.match_partner_ids
                and partner.commercial_partner_id not in self.match_partner_ids.commercial_partner_id):
            return False
        return True

    def _om_get_proposal(self, st_line):
        """ Proposal (see `account.bank.statement.line._om_reconcile`) of the model for the transaction. """
        self.ensure_one()
        if self.rule_type == 'matching_rule':
            return self._om_get_matching_rule_proposal(st_line)
        return {'writeoffs': self._om_get_writeoffs(st_line)}

    def _om_get_writeoffs(self, st_line, residual=None, partner=None):
        """ Counterparts of the lines of the model.

        :param residual: amount left to cover, as a journal item amount in transaction currency;
                         what is left on the suspense account of the transaction by default.
        :param partner: partner of the counterparts without a partner of their own;
                        the partner of the transaction by default.
        """
        self.ensure_one()
        if partner is None:
            partner = st_line.partner_id
        trans_currency, _company_currency = st_line._om_currencies()
        if residual is None:
            residual = st_line.amount_residual
        trans_amount = -(st_line.amount_currency if st_line.foreign_currency_id else st_line.amount)
        writeoffs = []
        for line in self.line_ids.filtered('account_id'):
            if line.amount_type == 'fixed':
                amount = -line.amount
            elif line.amount_type == 'percentage':
                amount = residual * line.amount / 100.0
            elif line.amount_type == 'percentage_st_line':
                amount = trans_amount * line.amount / 100.0
            else:
                amount = self._om_amount_from_label(st_line, line.amount_string)
                if amount is None:
                    continue
                amount = amount if trans_amount >= 0 else -amount
            amount = trans_currency.round(amount)
            if trans_currency.is_zero(amount):
                continue
            writeoffs.append({
                'account_id': line.account_id.id,
                'amount': amount,
                'label': line.label or st_line.payment_ref,
                'partner_id': (line.partner_id or partner).id,
                'tax_ids': line.tax_ids.ids,
                'tax_included': bool(line.tax_ids),
                'analytic_distribution': line.analytic_distribution or False,
                'reconcile_model_id': self.id,
            })
            residual -= amount
        return writeoffs

    def _om_amount_from_label(self, st_line, pattern):
        for text in self._om_label_texts(st_line):
            match = re.search(pattern, text)
            if not match:
                continue
            groups = [group for group in match.groups() if group is not None] or [match.group(0)]
            try:
                if len(groups) >= 2:
                    return float('%s.%s' % (re.sub(r'\D', '', groups[0]), re.sub(r'\D', '', groups[1])))
                value = groups[0].strip()
                if ',' in value and '.' in value:
                    value = (value.replace(',', '') if value.rfind('.') > value.rfind(',')
                             else value.replace('.', '').replace(',', '.'))
                else:
                    value = value.replace(',', '.')
                return abs(float(value))
            except ValueError:
                continue
        return None

    def _om_get_matching_rule_proposal(self, st_line):
        """ Open items of the partner of the transaction matching its amount within the payment tolerance,
        the difference being written off with the lines of the model. """
        self.ensure_one()
        partner = st_line.partner_id.commercial_partner_id
        if not partner:
            return {}
        trans_currency, _company_currency = st_line._om_currencies()
        residual = -st_line.amount_residual
        if trans_currency.is_zero(residual):
            return {}
        amls = self.env['account.move.line'].search(
            st_line._om_candidates_domain() + [
                ('partner_id', 'child_of', partner.id),
                ('account_id.account_type', 'in',
                 ('asset_receivable', 'liability_payable', 'asset_current', 'liability_current')),
            ],
            order='date_maturity %s, date %s, id' % (
                ('asc', 'asc') if self.matching_order == 'old_first' else ('desc', 'desc')
            ),
        )
        amls = amls.filtered(lambda aml: (aml.amount_residual > 0) == (residual > 0))
        tolerance = (self.payment_tolerance if self.payment_tolerance_type == 'amount'
                     else abs(residual) * self.payment_tolerance / 100.0)

        selected = self.env['account.move.line']
        total = 0.0
        for aml in amls:
            aml_amount = st_line._om_to_transaction_amount(
                aml.currency_id, aml.amount_residual_currency, aml.amount_residual,
            )
            total += aml_amount
            selected |= aml
            difference = trans_currency.round(abs(residual) - abs(total))
            if abs(difference) <= tolerance + trans_currency.rounding / 2:
                # matched in full: the difference within the tolerance is written off below
                proposal = {
                    'matches': [{'aml_id': aml.id, 'amount': abs(aml.amount_residual_currency)} for aml in selected],
                }
                if not trans_currency.is_zero(difference):
                    if not self.line_ids.filtered('account_id'):
                        return {}
                    # what the matched items do not cover, as a journal item amount
                    left = trans_currency.round(residual - total)
                    proposal['writeoffs'] = self._om_get_writeoffs(st_line, residual=-left)
                return proposal
            if abs(total) > abs(residual) + tolerance:
                break
        return {}
