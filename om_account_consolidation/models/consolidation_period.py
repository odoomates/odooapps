from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval

from .consolidation_group import ELIMINATIONS

PERIOD_TYPES = [
    ('month', "Month"),
    ('quarter', "Quarter"),
    ('year', "Fiscal Year"),
    ('custom', "Custom"),
]
LINE_KINDS = [
    ('balance', "Balance"),
    ('translation', "Translation Reserve"),
    ('elimination', "Elimination"),
    ('difference', "Elimination Difference"),
]


class OmConsolidationPeriod(models.Model):
    """The consolidation of a group over a period: the rates, the translated balances of every
    company, the eliminations and the manual adjustments. Computed, then approved and locked."""
    _name = 'om.consolidation.period'
    _description = 'Consolidation Period'
    _inherit = ['mail.thread']
    _order = 'date_to desc, id desc'

    name = fields.Char(compute='_compute_name', store=True, readonly=False, precompute=True, required=True)
    group_id = fields.Many2one('om.consolidation.group', string="Group", required=True, index=True,
                               ondelete='cascade', tracking=True)
    company_id = fields.Many2one(related='group_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='group_id.currency_id', string="Group Currency")
    period_type = fields.Selection(PERIOD_TYPES, string="Period", required=True, default='quarter')
    date_from = fields.Date(string="From", required=True, default=lambda self: self._om_default_date_from(),
                            tracking=True)
    date_to = fields.Date(string="To", compute='_compute_date_to', store=True, readonly=False, precompute=True, required=True,
                          tracking=True)
    state = fields.Selection(
        [('draft', "Draft"), ('computed', "Computed"), ('approved', "Approved")], string="Status",
        required=True, default='draft', tracking=True, copy=False)
    rate_ids = fields.One2many('om.consolidation.rate', 'period_id', string="Rates", copy=False)
    line_ids = fields.One2many('om.consolidation.line', 'period_id', string="Lines", copy=False)
    pair_ids = fields.One2many('om.consolidation.pair', 'period_id', string="Inter-Company Pairs", copy=False)
    adjustment_ids = fields.One2many('om.consolidation.adjustment', 'period_id', string="Adjustments", copy=False)
    computed_on = fields.Datetime(readonly=True, copy=False)
    computed_by_id = fields.Many2one('res.users', string="Computed By", readonly=True, copy=False)
    approved_on = fields.Datetime(readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', string="Approved By", readonly=True, copy=False)
    warning = fields.Text(readonly=True, copy=False,
                          help="What the last computation could not do as configured.")
    difference_count = fields.Integer(compute='_compute_differences', string="Pairs with a Difference")
    difference_amount = fields.Monetary(compute='_compute_differences', string="Elimination Differences")
    adjustment_count = fields.Integer(compute='_compute_adjustment_count')

    _om_dates_check = models.Constraint('CHECK(date_from <= date_to)', "A period starts before it ends.")

    @api.model
    def _om_default_date_from(self):
        today = fields.Date.context_today(self)
        start = today.replace(month=3 * ((today.month - 1) // 3) + 1, day=1)
        return start - relativedelta(months=3)

    @api.depends('period_type', 'date_from', 'group_id')
    def _compute_date_to(self):
        for period in self:
            start = period.date_from
            if not start:
                continue
            if period.period_type == 'month':
                period.date_to = start + relativedelta(months=1, days=-1)
            elif period.period_type == 'quarter':
                period.date_to = start + relativedelta(months=3, days=-1)
            elif period.period_type == 'year':
                company = period.group_id._om_rate_company() if period.group_id else self.env.company
                period.date_to = company.compute_fiscalyear_dates(start)['date_to']
            elif not period.date_to or period.date_to < start:
                period.date_to = start

    @api.onchange('period_type', 'group_id')
    def _onchange_period_type(self):
        # a fiscal year starts on the first day of the fiscal year of the parent company
        if self.period_type == 'year' and self.date_from:
            company = self.group_id._om_rate_company() if self.group_id else self.env.company
            self.date_from = company.compute_fiscalyear_dates(self.date_from)['date_from']
        elif self.period_type in ('month', 'quarter') and self.date_from:
            start = self.date_from.replace(day=1)
            if self.period_type == 'quarter':
                start = start.replace(month=3 * ((start.month - 1) // 3) + 1)
            self.date_from = start

    @api.depends('period_type', 'date_from', 'date_to')
    def _compute_name(self):
        for period in self:
            start, end = period.date_from, period.date_to
            if not start or not end:
                period.name = period.name or False
            elif period.period_type == 'month':
                period.name = start.strftime('%m/%Y')
            elif period.period_type == 'quarter':
                period.name = self.env._("Q%(quarter)s %(year)s", quarter=(start.month - 1) // 3 + 1, year=start.year)
            elif period.period_type == 'year':
                period.name = self.env._("FY %s", end.year if start.year == end.year else '%s-%s' % (start.year, end.year))
            else:
                period.name = '%s - %s' % (fields.Date.to_string(start), fields.Date.to_string(end))

    @api.depends('pair_ids.difference')
    def _compute_differences(self):
        for period in self:
            pairs = period.pair_ids.filtered(lambda pair: not period.currency_id.is_zero(pair.difference))
            period.difference_count = len(pairs)
            period.difference_amount = sum(abs(pair.difference) for pair in pairs)

    def _compute_adjustment_count(self):
        counts = dict(self.env['om.consolidation.adjustment']._read_group(
            [('period_id', 'in', self.ids)], ['period_id'], ['__count']))
        for period in self:
            period.adjustment_count = counts.get(period, 0)

    @api.constrains('group_id', 'date_from', 'date_to')
    def _check_overlap(self):
        for period in self:
            if self.search_count([('id', '!=', period.id), ('group_id', '=', period.group_id.id),
                                  ('date_from', '=', period.date_from), ('date_to', '=', period.date_to)]):
                raise ValidationError(self.env._("The group %s already has a period with these dates.",
                                                 period.group_id.name))

    def write(self, vals):
        locked = {'group_id', 'period_type', 'date_from', 'date_to'}
        if locked & set(vals) and self.filtered(lambda period: period.state == 'approved'):
            raise UserError(self.env._("An approved period is locked: reopen it to change it."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        if self.filtered(lambda period: period.state == 'approved'):
            raise UserError(self.env._("An approved period is locked: reopen it before deleting it."))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _om_check_editable(self):
        for period in self:
            if period.state == 'approved':
                raise UserError(self.env._("The period %(period)s of %(group)s is approved and locked. Reopen it "
                                           "to change it.", period=period.name, group=period.group_id.name))

    def action_compute(self):
        for period in self:
            period._om_check_editable()
            period.group_id._om_check_member_access()
            period._om_compute()
        return True

    def action_approve(self):
        for period in self:
            if period.state != 'computed':
                raise UserError(self.env._("Compute the period %s before approving it.", period.name))
            period.group_id._om_check_member_access()
        self.write({'state': 'approved', 'approved_on': fields.Datetime.now(), 'approved_by_id': self.env.uid})
        return True

    def action_reopen(self):
        for period in self:
            period.group_id._om_check_member_access()
        self.filtered(lambda period: period.state == 'approved').write(
            {'state': 'computed', 'approved_on': False, 'approved_by_id': False})
        return True

    def action_reset_to_draft(self):
        self._om_check_editable()
        self.line_ids.unlink()
        self.pair_ids.unlink()
        self.write({'state': 'draft', 'computed_on': False, 'computed_by_id': False, 'warning': False})
        return True

    def action_update_rates(self):
        self._om_check_editable()
        for period in self:
            period.group_id._om_check_member_access()
            period._om_update_rates(force=True)
        return True

    def action_check_mapping(self):
        self.ensure_one()
        self.group_id._om_check_member_access()
        return self.env['om.consolidation.unmapped']._om_open(self.group_id, self.date_to, self.date_from)

    def _om_report_action(self, xmlid):
        self.ensure_one()
        action = self.env['ir.actions.client']._for_xml_id(xmlid)
        action['context'] = {**safe_eval(action.get('context') or '{}'), 'om_options': {'period_id': str(self.id)}}
        action.pop('path', None)
        return action

    def action_open_trial_balance(self):
        return self._om_report_action('om_account_consolidation.action_om_consolidation_trial_balance')

    def action_open_profit_loss(self):
        return self._om_report_action('om_account_consolidation.action_om_consolidation_profit_loss')

    def action_open_balance_sheet(self):
        return self._om_report_action('om_account_consolidation.action_om_consolidation_balance_sheet')

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Consolidation Lines"),
            'res_model': 'om.consolidation.line',
            'view_mode': 'list,pivot',
            'domain': [('period_id', '=', self.id)],
            'context': {'create': False, 'search_default_group_by_group_account': 1},
        }

    def action_open_adjustments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Adjustments"),
            'res_model': 'om.consolidation.adjustment',
            'view_mode': 'list,form',
            'domain': [('period_id', '=', self.id)],
            'context': {'default_period_id': self.id},
        }

    # ------------------------------------------------------------------
    # Rates
    # ------------------------------------------------------------------

    def _om_closing_rate(self, company):
        """The group currency for one unit of the currency of ``company``, at the end of the last day
        of the period (a rate applies from the day after its date)."""
        group = self.group_id
        return self.env['res.currency']._get_conversion_rate(
            company.currency_id, group.currency_id, group._om_rate_company(), self.date_to + timedelta(days=1))

    def _om_average_rate(self, company):
        """The average of the rates of the days of the period, each rate weighed by the days it applies."""
        group = self.group_id
        source, target = company.currency_id, group.currency_id
        if source == target:
            return 1.0
        rate_company = group._om_rate_company().root_id
        Currency = self.env['res.currency']
        changes = self.env['res.currency.rate'].sudo().search([
            ('currency_id', 'in', (source | target).ids), ('company_id', 'in', (False, rate_company.id)),
            ('name', '>', self.date_from), ('name', '<=', self.date_to)])
        starts = sorted({self.date_from} | set(changes.mapped('name')))
        total = 0.0
        for index, start in enumerate(starts):
            end = starts[index + 1] - timedelta(days=1) if index + 1 < len(starts) else self.date_to
            # the rate of a day is the last rate dated that day or before
            rate = Currency._get_conversion_rate(source, target, rate_company, start + timedelta(days=1))
            total += rate * ((end - start).days + 1)
        return total / ((self.date_to - self.date_from).days + 1)

    def _om_update_rates(self, force=False):
        """The closing and average rate of every company, from the currency rates; the rates entered by
        hand are kept unless ``force``."""
        self.ensure_one()
        Rate = self.env['om.consolidation.rate']
        rates = {rate.company_id: rate for rate in self.rate_ids}
        for company in self.group_id.member_ids.company_id:
            rate = rates.get(company)
            if rate and rate.manual and not force:
                continue
            values = {'closing_rate': self._om_closing_rate(company), 'average_rate': self._om_average_rate(company),
                      'manual': False}
            if rate:
                rate.write(values)
            else:
                Rate.create({**values, 'period_id': self.id, 'company_id': company.id})
        (self.rate_ids - self.rate_ids.filtered(lambda r: r.company_id in self.group_id.member_ids.company_id)).unlink()

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def _om_previous_period(self):
        """The last computed period of the group before this one: the equity carried over from it."""
        self.ensure_one()
        return self.search([('group_id', '=', self.group_id.id), ('date_to', '<', self.date_from),
                            ('state', 'in', ('computed', 'approved'))], order='date_to desc', limit=1)

    def _om_check_setup(self):
        group = self.group_id
        if not group.member_ids:
            raise UserError(self.env._("Add the companies of the group %s first.", group.name))
        missing = [label for label, account in (
            (self.env._("Retained Earnings"), group.retained_earnings_account_id),
            (self.env._("Translation Reserve"), group.translation_account_id),
            (self.env._("Elimination Differences"), group.difference_account_id)) if not account]
        if missing:
            raise UserError(self.env._(
                "Set the group accounts of the group %(group)s first: %(accounts)s.",
                group=group.name, accounts=', '.join(missing)))
        unmapped = group._om_unmapped(self.date_to, self.date_from)
        if unmapped:
            listed = ['%s: %s (%s)' % (company.name, ' '.join(filter(None, [account.with_company(company).code,
                                                                        account.name])),
                                       company.currency_id.format(balance))
                      for company, account, balance in unmapped[:10]]
            if len(unmapped) > 10:
                listed.append(self.env._("... and %s more", len(unmapped) - 10))
            raise UserError(self.env._(
                "These accounts have a balance and map to no account of the group chart. Map them, then compute "
                "again (Check Mapping lists them all):\n%s", '\n'.join(listed)))

    def _om_company_figures(self, company, mapping, eliminated):
        """The figures of one company, in its currency:
        - balances: {account id: balance}: the balance at the end of the period of the balance sheet
          accounts, the movements of the period of the income and expense accounts;
        - earlier: the income and expense before the period;
        - inter_company: {(type, account id, other company id): amount} of the journal items with the
          other companies of the group on the accounts of eliminated group accounts (the movements of the
          period for dividends, with no other company)."""
        group = self.group_id
        MoveLine = self.env['account.move.line'].with_context(allowed_company_ids=group.member_ids.company_id.ids)
        base = Domain([('company_id', '=', company.id), ('parent_state', '=', 'posted'),
                       ('account_id.account_type', '!=', 'off_balance'), ('date', '<=', self.date_to)])
        balance_sheet = Domain('account_id.include_initial_balance', '=', True)
        profit_loss = Domain('account_id.include_initial_balance', '=', False)
        in_period = Domain('date', '>=', self.date_from)
        balances = {}
        for account, balance in MoveLine._read_group(
                base & (balance_sheet | (profit_loss & in_period)), ['account_id'], ['balance:sum']):
            balances[account.id] = balance
        [[earlier]] = MoveLine._read_group(base & profit_loss & Domain('date', '<', self.date_from), [],
                                           ['balance:sum'])

        inter_company = defaultdict(float)
        members = group.member_ids.company_id
        by_type = defaultdict(list)
        for account_id, group_account in mapping.items():
            if group_account.elimination in eliminated:
                by_type[group_account.elimination].append(account_id)
        for kind in ('balance', 'flow'):
            if not by_type[kind]:
                continue
            domain = base & Domain('account_id', 'in', by_type[kind]) & Domain('partner_id', '!=', False)
            if kind == 'flow':
                domain &= in_period
            for account, partner, balance in MoveLine._read_group(
                    domain & (balance_sheet | in_period), ['account_id', 'partner_id'], ['balance:sum']):
                other = partner._om_ic_company()
                if other and other in members and other != company:
                    inter_company[(kind, account.id, other.id)] += balance
        if by_type['dividend']:
            for account, balance in MoveLine._read_group(
                    base & in_period & Domain('account_id', 'in', by_type['dividend']), ['account_id'],
                    ['balance:sum']):
                inter_company[('dividend', account.id, False)] += balance
        return balances, earlier or 0.0, inter_company

    def _om_compute(self):
        """Translate the balances of every company into the group currency, put the translation
        differences to the translation reserve, and eliminate what the companies of the group owe
        each other, sold to each other and paid each other as dividends."""
        self.ensure_one()
        self._om_check_setup()
        self._om_update_rates()
        group = self.group_id
        currency = group.currency_id
        rates = {rate.company_id: rate for rate in self.rate_ids}
        historical = {(rate.company_id.id, rate.group_account_id.id): rate.rate for rate in group.historical_rate_ids}
        previous = self._om_previous_period()
        carried = {}
        for line in previous.line_ids.filtered(lambda line: line.kind == 'balance'):
            carried[(line.company_id.id, line.account_id.id, line.group_account_id.id)] = (
                line.closing_amount, line.closing_translated)
        warnings = []
        lines = []
        pair_amounts = defaultdict(float)
        eliminated = {'balance', 'flow', 'dividend'}

        for company in group.member_ids.company_id:
            rate = rates[company]
            mapping = group._om_account_map(company)
            balances, earlier, inter_company = self._om_company_figures(company, mapping, eliminated)
            Account = self.env['account.account'].with_company(company)
            figures = [(Account.browse(account_id), mapping[account_id], amount)
                       for account_id, amount in balances.items() if account_id in mapping]
            if not company.currency_id.is_zero(earlier):
                figures.append((Account, group.retained_earnings_account_id, earlier))
            effective = {}
            company_lines = []
            profit = profit_translated = 0.0
            for account, group_account, amount in figures:
                if company.currency_id.is_zero(amount) and (company.id, account.id, group_account.id) not in carried:
                    continue
                translated, line_rate = self._om_translate(
                    company, account, group_account, amount, rate, historical, carried, warnings)
                effective[account.id] = line_rate
                values = {
                    'period_id': self.id, 'kind': 'balance', 'company_id': company.id, 'account_id': account.id,
                    'group_account_id': group_account.id, 'amount': amount, 'rate': line_rate,
                    'translated': translated, 'closing_amount': amount, 'closing_translated': translated,
                }
                if group_account.kind in ('income', 'expense'):
                    profit += amount
                    profit_translated += translated
                company_lines.append(values)
            # the result of the period goes to the retained earnings of the next one
            retained = next((values for values in company_lines if not values['account_id']
                             and values['group_account_id'] == group.retained_earnings_account_id.id), None)
            if retained is None and not (company.currency_id.is_zero(profit) and currency.is_zero(profit_translated)):
                retained = {
                    'period_id': self.id, 'kind': 'balance', 'company_id': company.id, 'account_id': False,
                    'group_account_id': group.retained_earnings_account_id.id, 'amount': 0.0, 'rate': 0.0,
                    'translated': 0.0, 'closing_amount': 0.0, 'closing_translated': 0.0,
                }
                company_lines.append(retained)
            if retained is not None:
                retained['closing_amount'] += profit
                retained['closing_translated'] += profit_translated
            lines += company_lines
            reserve = -sum(values['translated'] for values in company_lines)
            if not currency.is_zero(reserve):
                lines.append({
                    'period_id': self.id, 'kind': 'translation', 'company_id': company.id,
                    'group_account_id': group.translation_account_id.id, 'amount': 0.0, 'rate': 0.0,
                    'translated': currency.round(reserve), 'closing_amount': 0.0,
                    'closing_translated': currency.round(reserve),
                })

            # eliminations, at the rate the balance was translated at (the average rate for dividends)
            for (kind, account_id, other_id), amount in inter_company.items():
                if company.currency_id.is_zero(amount):
                    continue
                group_account = mapping[account_id]
                line_rate = rate.average_rate if kind == 'dividend' else effective.get(
                    account_id, self._om_type_rate(group_account, rate))
                translated = currency.round(amount * line_rate)
                lines.append({
                    'period_id': self.id, 'kind': 'elimination', 'elimination': kind, 'company_id': company.id,
                    'partner_company_id': other_id, 'account_id': account_id, 'group_account_id': group_account.id,
                    'amount': -amount, 'rate': line_rate, 'translated': -translated,
                })
                pair_amounts[(kind, company.id, other_id)] += translated

        pairs, differences = self._om_pairs(pair_amounts)
        for (kind, company_id, other_id), difference in differences.items():
            if currency.is_zero(difference):
                continue
            lines.append({
                'period_id': self.id, 'kind': 'difference', 'elimination': kind, 'company_id': company_id,
                'partner_company_id': other_id, 'group_account_id': group.difference_account_id.id,
                'amount': 0.0, 'rate': 0.0, 'translated': difference,
            })
        self.line_ids.unlink()
        self.pair_ids.unlink()
        self.env['om.consolidation.line'].create(lines)
        self.env['om.consolidation.pair'].create([{**pair, 'period_id': self.id} for pair in pairs])
        self.write({'state': 'computed', 'computed_on': fields.Datetime.now(), 'computed_by_id': self.env.uid,
                    'warning': '\n'.join(dict.fromkeys(warnings)) or False})

    def _om_type_rate(self, group_account, rate):
        if group_account.rate_type == 'average':
            return rate.average_rate
        return rate.closing_rate

    def _om_translate(self, company, account, group_account, amount, rate, historical, carried, warnings):
        """(translated amount, rate) of one balance."""
        currency = self.group_id.currency_id
        if group_account.rate_type != 'historical':
            line_rate = self._om_type_rate(group_account, rate)
            return currency.round(amount * line_rate), line_rate
        line_rate = historical.get((company.id, group_account.id)) or historical.get((company.id, False))
        if line_rate:
            return currency.round(amount * line_rate), line_rate
        key = (company.id, account.id, group_account.id)
        if key in carried:
            # the equity of the previous period, and its movements since at the average rate
            previous_amount, previous_translated = carried[key]
            translated = currency.round(previous_translated + (amount - previous_amount) * rate.average_rate)
            return translated, translated / amount if amount else 0.0
        if company.currency_id != currency:
            warnings.append(self.env._(
                "%(company)s: %(account)s has no historical rate and no previous period: translated at the "
                "closing rate.", company=company.name, account=group_account.display_name))
        return currency.round(amount * rate.closing_rate), rate.closing_rate

    def _om_pairs(self, pair_amounts):
        """The inter-company pairs as both companies book them, and the differences that make the
        eliminations balance: {(type, company, other company): difference}."""
        pairs = []
        differences = {}
        seen = set()
        sequence = {member.company_id.id: index for index, member in enumerate(self.group_id.member_ids)}
        for (kind, company_id, other_id) in pair_amounts:
            if kind == 'dividend':
                continue
            first, second = sorted((company_id, other_id), key=lambda cid: sequence.get(cid, 0))
            if (kind, first, second) in seen:
                continue
            seen.add((kind, first, second))
            own = pair_amounts.get((kind, first, second), 0.0)
            their = pair_amounts.get((kind, second, first), 0.0)
            pairs.append({'elimination': kind, 'company_id': first, 'partner_company_id': second,
                          'amount': own, 'partner_amount': -their})
            differences[(kind, first, second)] = own + their
        dividends = sum(amount for (kind, _company, _other), amount in pair_amounts.items() if kind == 'dividend')
        if dividends:
            differences[('dividend', False, False)] = dividends
        return pairs, differences

    # ------------------------------------------------------------------
    # Journal items behind a figure
    # ------------------------------------------------------------------

    def _om_items_domain(self, company, accounts, earlier=False):
        """The journal items of ``company`` behind the balances of ``accounts``: up to the end of the
        period for the balance sheet accounts, of the period for the income and expense; with
        ``earlier``, also the income and expense before the period (in the retained earnings)."""
        self.ensure_one()
        base = Domain([('company_id', '=', company.id), ('parent_state', '=', 'posted'),
                       ('date', '<=', self.date_to)])
        scopes = []
        if accounts:
            scopes.append(Domain('account_id', 'in', accounts.ids) & (
                Domain('account_id.include_initial_balance', '=', True) | Domain('date', '>=', self.date_from)))
        if earlier:
            scopes.append(Domain([('account_id.include_initial_balance', '=', False),
                                  ('account_id.account_type', '!=', 'off_balance'),
                                  ('date', '<', self.date_from)]))
        if not scopes:
            return False
        return list(base & Domain.OR(scopes))


class OmConsolidationRate(models.Model):
    _name = 'om.consolidation.rate'
    _description = 'Consolidation Rate'
    _order = 'period_id, company_id'

    period_id = fields.Many2one('om.consolidation.period', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string="Company", required=True)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Currency")
    group_currency_id = fields.Many2one(related='period_id.currency_id', string="Group Currency")
    closing_rate = fields.Float(string="Closing Rate", digits=0,
                                help="The group currency for one unit of the currency of the company, at the end "
                                     "of the period: for assets and liabilities.")
    average_rate = fields.Float(string="Average Rate", digits=0,
                                help="The average of the rates of the days of the period: for income and expense.")
    manual = fields.Boolean(string="Entered", help="The rates were entered by hand: computing the period keeps them.")

    _om_company_uniq = models.Constraint('UNIQUE(period_id, company_id)', "A company has one rate per period.")

    @api.onchange('closing_rate', 'average_rate')
    def _onchange_rates(self):
        self.manual = True

    def write(self, vals):
        if self.period_id.filtered(lambda period: period.state == 'approved'):
            raise UserError(self.env._("An approved period is locked: reopen it to change its rates."))
        return super().write(vals)


class OmConsolidationLine(models.Model):
    """A figure of a consolidation: the translated balance of an account of a company, the translation
    reserve of a company, an elimination or an elimination difference."""
    _name = 'om.consolidation.line'
    _description = 'Consolidation Line'
    _order = 'group_account_id, company_id, id'

    period_id = fields.Many2one('om.consolidation.period', required=True, ondelete='cascade', index=True)
    group_id = fields.Many2one(related='period_id.group_id', store=True)
    company_id = fields.Many2one('res.company', string="Company", index=True)
    kind = fields.Selection(LINE_KINDS, string="Type", required=True)
    elimination = fields.Selection(ELIMINATIONS, string="Elimination")
    partner_company_id = fields.Many2one('res.company', string="Other Company")
    account_id = fields.Many2one('account.account', string="Account", help="The account of the company.")
    group_account_id = fields.Many2one('om.consolidation.account', string="Group Account", required=True,
                                       ondelete='cascade', index=True)
    company_currency_id = fields.Many2one(related='company_id.currency_id', string="Company Currency")
    currency_id = fields.Many2one(related='period_id.currency_id', string="Group Currency")
    amount = fields.Monetary(currency_field='company_currency_id', string="Amount",
                             help="In the currency of the company.")
    rate = fields.Float(digits=0)
    translated = fields.Monetary(currency_field='currency_id', string="Translated", help="In the group currency.")
    closing_amount = fields.Monetary(currency_field='company_currency_id',
                                     help="Carried over to the next period (with the result of the period).")
    closing_translated = fields.Monetary(currency_field='currency_id')

    @api.depends('kind', 'account_id', 'company_id', 'partner_company_id')
    def _compute_display_name(self):
        for line in self:
            line.display_name = line._om_label()

    def _om_label(self):
        self.ensure_one()
        if self.kind == 'balance':
            if not self.account_id:
                return self.env._("%s: income and expense of previous periods", self.company_id.name)
            code = self.account_id.with_company(self.company_id).code
            return '%s: %s' % (self.company_id.name, ' '.join(filter(None, [code, self.account_id.name])))
        if self.kind == 'translation':
            return self.env._("%s: translation difference", self.company_id.name)
        label = dict(self._fields['elimination']._description_selection(self.env)).get(self.elimination, '')
        if self.kind == 'difference':
            if self.company_id and self.partner_company_id:
                return self.env._("Difference: %(company)s / %(other)s (%(type)s)", company=self.company_id.name,
                                  other=self.partner_company_id.name, type=label)
            return self.env._("Difference (%s)", label)
        if self.partner_company_id:
            return self.env._("%(type)s: %(company)s with %(other)s", type=label, company=self.company_id.name,
                              other=self.partner_company_id.name)
        return '%s: %s' % (label, self.company_id.name)


class OmConsolidationPair(models.Model):
    """What two companies of the group book with each other, translated: the elimination balances
    when both agree."""
    _name = 'om.consolidation.pair'
    _description = 'Consolidation Inter-Company Pair'
    _order = 'elimination, company_id, partner_company_id'

    period_id = fields.Many2one('om.consolidation.period', required=True, ondelete='cascade', index=True)
    elimination = fields.Selection(ELIMINATIONS, string="Type", required=True)
    company_id = fields.Many2one('res.company', string="Company", required=True)
    partner_company_id = fields.Many2one('res.company', string="Other Company", required=True)
    currency_id = fields.Many2one(related='period_id.currency_id', string="Group Currency")
    amount = fields.Monetary(string="Company Books",
                             help="What the company books with the other company (owed to it, or sold to it).")
    partner_amount = fields.Monetary(string="Other Company Books",
                                     help="The same, as the other company books it, with the sign of the company.")
    difference = fields.Monetary(compute='_compute_difference', store=True)

    @api.depends('amount', 'partner_amount')
    def _compute_difference(self):
        for pair in self:
            pair.difference = pair.amount - pair.partner_amount


class OmConsolidationAdjustment(models.Model):
    """A manual entry of a consolidation period, on group accounts, for what the eliminations do not do."""
    _name = 'om.consolidation.adjustment'
    _description = 'Consolidation Adjustment'
    _order = 'period_id, id'

    name = fields.Char(string="Reference", required=True)
    period_id = fields.Many2one('om.consolidation.period', string="Period", required=True, ondelete='cascade',
                                index=True)
    group_id = fields.Many2one(related='period_id.group_id', store=True)
    company_id = fields.Many2one(related='period_id.company_id', store=True)
    currency_id = fields.Many2one(related='period_id.currency_id', string="Group Currency")
    state = fields.Selection(related='period_id.state', string="Period Status")
    line_ids = fields.One2many('om.consolidation.adjustment.line', 'adjustment_id', string="Lines", copy=True)
    total = fields.Monetary(compute='_compute_total', string="Amount")
    note = fields.Text(string="Notes")

    @api.depends('line_ids.debit')
    def _compute_total(self):
        for adjustment in self:
            adjustment.total = sum(adjustment.line_ids.mapped('debit'))

    @api.constrains('line_ids')
    def _check_balanced(self):
        for adjustment in self:
            balance = sum(adjustment.line_ids.mapped('debit')) - sum(adjustment.line_ids.mapped('credit'))
            if not adjustment.currency_id.is_zero(balance):
                raise ValidationError(self.env._(
                    "The adjustment %(name)s does not balance: the debits and the credits differ by %(amount)s.",
                    name=adjustment.name, amount=adjustment.currency_id.format(balance)))

    def _om_check_editable(self):
        self.period_id._om_check_editable()

    @api.model_create_multi
    def create(self, vals_list):
        adjustments = super().create(vals_list)
        adjustments._om_check_editable()
        return adjustments

    def write(self, vals):
        self._om_check_editable()
        result = super().write(vals)
        self._om_check_editable()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        self._om_check_editable()


class OmConsolidationAdjustmentLine(models.Model):
    _name = 'om.consolidation.adjustment.line'
    _description = 'Consolidation Adjustment Line'
    _order = 'adjustment_id, sequence, id'

    adjustment_id = fields.Many2one('om.consolidation.adjustment', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    period_id = fields.Many2one(related='adjustment_id.period_id', store=True, index=True)
    group_id = fields.Many2one(related='adjustment_id.group_id')
    group_account_id = fields.Many2one(
        'om.consolidation.account', string="Group Account", required=True, ondelete='restrict',
        domain="[('group_id', '=', group_id)]")
    company_id = fields.Many2one(
        'res.company', string="Company", help="The company the adjustment belongs to. Empty: the group.")
    name = fields.Char(string="Label")
    currency_id = fields.Many2one(related='adjustment_id.currency_id', string="Group Currency")
    debit = fields.Monetary()
    credit = fields.Monetary()

    @api.constrains('group_account_id', 'company_id')
    def _check_group(self):
        for line in self:
            group = line.adjustment_id.group_id
            if line.group_account_id.group_id != group:
                raise ValidationError(self.env._("An adjustment uses the accounts of the group of its period."))
            if line.company_id and line.company_id not in group.member_ids.company_id:
                raise ValidationError(self.env._("%s is not a company of the group.", line.company_id.name))

    def _om_check_editable(self):
        self.period_id._om_check_editable()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._om_check_editable()
        return lines

    def write(self, vals):
        self._om_check_editable()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approved(self):
        self._om_check_editable()
