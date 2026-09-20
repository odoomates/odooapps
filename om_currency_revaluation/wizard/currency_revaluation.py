from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL
from odoo.tools.misc import format_date

# the accounts revalued from what is still open on them, the other ones from the balance they hold
OPEN_ITEM_TYPES = ('asset_receivable', 'liability_payable')


class CurrencyRevaluation(models.TransientModel):
    _name = 'currency.revaluation'
    _description = 'Currency Revaluation'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(
        string='Revaluation Date', required=True, default=fields.Date.context_today,
        help="The open balances are revalued at the rate of this date, usually the last day of a period.")
    currency_ids = fields.Many2many(
        'res.currency', string='Currencies',
        help="Leave empty to revalue every currency other than the one of the company.")
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, check_company=True,
        compute='_compute_from_company', store=True, readonly=False, precompute=True,
        domain="[('type', '=', 'general')]")
    gain_account_id = fields.Many2one(
        'account.account', string='Unrealized Gain Account', required=True, check_company=True,
        compute='_compute_from_company', store=True, readonly=False, precompute=True)
    loss_account_id = fields.Many2one(
        'account.account', string='Unrealized Loss Account', required=True, check_company=True,
        compute='_compute_from_company', store=True, readonly=False, precompute=True)
    reverse = fields.Boolean(
        string='Reverse Next Period', compute='_compute_from_company', store=True, readonly=False,
        precompute=True)
    reversal_date = fields.Date(
        string='Reversal Date', compute='_compute_reversal_date', store=True, readonly=False,
        precompute=True)
    line_ids = fields.One2many(
        'currency.revaluation.line', 'revaluation_id', string='Revaluation',
        compute='_compute_line_ids', store=True)
    adjustment = fields.Monetary(
        string='Adjustment', compute='_compute_line_ids', store=True, currency_field='company_currency_id')

    @api.depends('company_id')
    def _compute_from_company(self):
        for wizard in self:
            company = wizard.company_id
            wizard.journal_id = company.currency_reval_journal_id
            wizard.gain_account_id = company.currency_reval_gain_account_id
            wizard.loss_account_id = company.currency_reval_loss_account_id
            wizard.reverse = company.currency_reval_reverse

    @api.depends('date')
    def _compute_reversal_date(self):
        for wizard in self:
            wizard.reversal_date = wizard.date and wizard.date + relativedelta(days=1)

    @api.depends('date', 'currency_ids', 'company_id')
    def _compute_line_ids(self):
        for wizard in self:
            values = wizard._get_revaluation_values()
            wizard.line_ids = [(5, 0, 0)] + [(0, 0, value) for value in values]
            wizard.adjustment = sum(value['adjustment'] for value in values)

    # -------------------------------------------------------------------------
    # Revaluation
    # -------------------------------------------------------------------------

    def _revaluation_domain(self):
        """ The journal items to revalue: what is posted in a foreign currency up to the date of the revaluation """
        self.ensure_one()
        domain = [
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('date', '<=', self.date),
            ('currency_id', '!=', self.company_currency_id.id),
            ('amount_currency', '!=', 0),
        ]
        if self.currency_ids:
            domain.append(('currency_id', 'in', self.currency_ids.ids))
        return domain

    def _get_revaluation_values(self):
        """ The amounts to adjust, one per account, partner and currency.

        The open items of the receivable and payable accounts are revalued for what is left on them at the date of
        the revaluation, the other accounts for the balance they hold on that date.

        :return: list of the values of `currency.revaluation.line`
        """
        self.ensure_one()
        if not self.date or not self.company_id:
            return []
        company = self.company_id
        company_currency = self.company_currency_id
        lines = self.env['account.move.line'].sudo().search(self._revaluation_domain())
        groups = {}
        for line, residual_currency, residual_balance in self._residuals_at_date(lines):
            if line.currency_id.is_zero(residual_currency):
                continue
            key = (line.account_id, line.partner_id if line.account_type in OPEN_ITEM_TYPES else
                   self.env['res.partner'], line.currency_id)
            group = groups.setdefault(key, {'amount_currency': 0.0, 'balance': 0.0})
            group['amount_currency'] += residual_currency
            group['balance'] += residual_balance
        values = []
        for (account, partner, currency), group in groups.items():
            if currency.is_zero(group['amount_currency']):
                continue
            revalued = currency._convert(group['amount_currency'], company_currency, company, self.date)
            adjustment = company_currency.round(revalued - group['balance'])
            if company_currency.is_zero(adjustment):
                continue
            values.append({
                'account_id': account.id,
                'partner_id': partner.id,
                'currency_id': currency.id,
                'amount_currency': group['amount_currency'],
                'balance': group['balance'],
                'revalued': revalued,
                'adjustment': adjustment,
            })
        return sorted(values, key=lambda value: (value['currency_id'], value['account_id'], value['partner_id']))

    def _residuals_at_date(self, lines):
        """ What was left on each journal item on the date of the revaluation: the amounts matched afterwards are
        not deducted, so that a revaluation of a past period stays the same once the invoices are paid.

        :return: [(line, residual in its currency, residual in the currency of the company)]
        """
        self.ensure_one()
        open_items = lines.filtered(lambda line: line.account_type in OPEN_ITEM_TYPES)
        matched = self._matched_at_date(open_items)
        for line in lines:
            if line.account_type in OPEN_ITEM_TYPES:
                paid_currency, paid_balance = matched.get(line.id, (0.0, 0.0))
                sign = 1 if line.balance > 0 else -1
                yield line, line.amount_currency - sign * paid_currency, line.balance - sign * paid_balance
            elif line.account_id.currency_id:
                # an account held in a foreign currency, such as a bank account: its whole balance is revalued
                yield line, line.amount_currency, line.balance

    def _matched_at_date(self, lines):
        """ :return: {line id: (amount matched in the currency of the line, in the currency of the company)} on the
        date of the revaluation, the amounts always positive """
        if not lines:
            return {}
        rows = self.env.execute_query(SQL(
            """
              SELECT part.debit_move_id AS line_id,
                     SUM(part.debit_amount_currency) AS amount_currency,
                     SUM(part.amount) AS balance
                FROM account_partial_reconcile part
                JOIN account_move_line credit_line ON credit_line.id = part.credit_move_id
                JOIN account_move_line debit_line ON debit_line.id = part.debit_move_id
               WHERE part.debit_move_id = ANY(%(ids)s)
                 AND GREATEST(credit_line.date, debit_line.date) <= %(date)s
            GROUP BY part.debit_move_id
               UNION ALL
              SELECT part.credit_move_id AS line_id,
                     SUM(part.credit_amount_currency) AS amount_currency,
                     SUM(part.amount) AS balance
                FROM account_partial_reconcile part
                JOIN account_move_line credit_line ON credit_line.id = part.credit_move_id
                JOIN account_move_line debit_line ON debit_line.id = part.debit_move_id
               WHERE part.credit_move_id = ANY(%(ids)s)
                 AND GREATEST(credit_line.date, debit_line.date) <= %(date)s
            GROUP BY part.credit_move_id
            """,
            ids=lines.ids, date=self.date,
        ))
        return {row[0]: (row[1], row[2]) for row in rows}

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_revalue(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_("Only the accounting managers can post a currency revaluation."))
        existing = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('currency_reval_date', '=', self.date),
            ('state', '!=', 'cancel'),
        ], limit=1)
        if existing:
            raise UserError(_(
                "The open balances are already revalued on %(date)s by the entry %(entry)s. Reverse or delete it "
                "before revaluing that date again.",
                date=format_date(self.env, self.date), entry=existing.display_name,
            ))
        values = self._get_revaluation_values()
        if not values:
            raise UserError(_("Nothing is open in a foreign currency to revalue on this date."))
        move = self.env['account.move'].create(self._get_move_values(values))
        move.action_post()
        if self.reverse:
            reversal = move._reverse_moves(default_values_list=[{
                'date': self.reversal_date,
                'ref': _('Reversal of the currency revaluation of %s', format_date(self.env, self.date)),
            }])
            reversal.action_post()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Currency Revaluation'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }

    def _get_move_values(self, values):
        """ :return: the values of the adjustment entry: the difference on each account, against the unrealized
        gain and loss accounts """
        self.ensure_one()
        company_currency = self.company_currency_id
        line_values = []
        gain = loss = 0.0
        for value in values:
            adjustment = value['adjustment']
            account = self.env['account.account'].browse(value['account_id'])
            currency = self.env['res.currency'].browse(value['currency_id'])
            if adjustment > 0:
                gain += adjustment
            else:
                loss -= adjustment
            line_values.append((0, 0, {
                'name': _('Revaluation of %(amount)s at the rate of %(date)s',
                          amount=currency.format(value['amount_currency']),
                          date=format_date(self.env, self.date)),
                'account_id': account.id,
                'partner_id': value['partner_id'],
                # the amount in the foreign currency does not change: only what it is worth does
                'currency_id': account.currency_id.id or company_currency.id,
                'amount_currency': 0.0 if account.currency_id else adjustment,
                'balance': adjustment,
            }))
        for amount, account in ((gain, self.gain_account_id), (loss, self.loss_account_id)):
            if company_currency.is_zero(amount):
                continue
            balance = -amount if account == self.gain_account_id else amount
            line_values.append((0, 0, {
                'name': _('Unrealized gain') if account == self.gain_account_id else _('Unrealized loss'),
                'account_id': account.id,
                'currency_id': account.currency_id.id or company_currency.id,
                'amount_currency': 0.0 if account.currency_id else balance,
                'balance': balance,
            }))
        return {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'date': self.date,
            'currency_reval_date': self.date,
            'ref': _('Currency revaluation of %s', format_date(self.env, self.date)),
            'line_ids': line_values,
        }


class CurrencyRevaluationLine(models.TransientModel):
    _name = 'currency.revaluation.line'
    _description = 'Currency Revaluation Line'
    _order = 'currency_id, account_id, partner_id'

    revaluation_id = fields.Many2one('currency.revaluation', required=True, ondelete='cascade')
    company_currency_id = fields.Many2one(
        related='revaluation_id.company_currency_id', string='Company Currency')
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    amount_currency = fields.Monetary(string='Open Amount', currency_field='currency_id', readonly=True)
    balance = fields.Monetary(string='In the Books', currency_field='company_currency_id', readonly=True)
    revalued = fields.Monetary(string='At the Closing Rate', currency_field='company_currency_id', readonly=True)
    adjustment = fields.Monetary(string='Adjustment', currency_field='company_currency_id', readonly=True)
