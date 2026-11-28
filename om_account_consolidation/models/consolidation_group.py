from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

ACCOUNT_KINDS = [
    ('asset', "Asset"),
    ('liability', "Liability"),
    ('equity', "Equity"),
    ('income', "Income"),
    ('expense', "Expense"),
]
BALANCE_SHEET_KINDS = ('asset', 'liability', 'equity')
RATE_TYPES = [
    ('closing', "Closing rate"),
    ('average', "Average rate"),
    ('historical', "Historical rate"),
]
ELIMINATIONS = [
    ('none', "None"),
    ('balance', "Inter-company balances"),
    ('flow', "Inter-company sales and purchases"),
    ('dividend', "Inter-company dividends"),
]
MAPPING_METHODS = [
    ('account', "Accounts"),
    ('range', "Code range"),
    ('type', "Account type"),
]
# the accounts mapped one by one come first, then the code ranges, then the account types
METHOD_PRIORITY = {'account': 0, 'range': 1, 'type': 2}

# the group chart a group starts with: (code, name, kind, elimination, account types mapped to it)
DEFAULT_CHART = [
    ('1100', _lt("Cash and Bank"), 'asset', 'none', ['asset_cash']),
    ('1200', _lt("Receivables"), 'asset', 'balance', ['asset_receivable']),
    ('1300', _lt("Other Current Assets"), 'asset', 'none', ['asset_current', 'asset_prepayments']),
    ('1500', _lt("Fixed and Non-current Assets"), 'asset', 'none', ['asset_fixed', 'asset_non_current']),
    ('2100', _lt("Payables"), 'liability', 'balance', ['liability_payable']),
    ('2200', _lt("Current Liabilities"), 'liability', 'none', ['liability_current', 'liability_credit_card']),
    ('2500', _lt("Non-current Liabilities"), 'liability', 'none', ['liability_non_current']),
    ('3100', _lt("Capital and Reserves"), 'equity', 'none', ['equity']),
    ('3200', _lt("Retained Earnings"), 'equity', 'none', ['equity_unaffected']),
    ('3300', _lt("Translation Reserve"), 'equity', 'none', []),
    ('4100', _lt("Revenue"), 'income', 'flow', ['income']),
    ('4200', _lt("Other Income"), 'income', 'none', ['income_other']),
    ('4300', _lt("Dividend Income"), 'income', 'dividend', []),
    ('5100', _lt("Cost of Sales"), 'expense', 'flow', ['expense_direct_cost']),
    ('5200', _lt("Operating Expenses"), 'expense', 'flow', ['expense']),
    ('5300', _lt("Depreciation"), 'expense', 'none', ['expense_depreciation']),
    ('5900', _lt("Elimination Differences"), 'expense', 'none', []),
]


class OmConsolidationGroup(models.Model):
    """A group of companies consolidated together: its member companies, its currency, its chart of
    accounts and how the accounts of each company map to it."""
    _name = 'om.consolidation.group'
    _description = 'Consolidation Group'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string="Managed By", required=True, default=lambda self: self.env.company,
        help="The company whose accounting managers run the consolidation: usually the parent company.")
    parent_company_id = fields.Many2one(
        'res.company', string="Parent Company", tracking=True,
        help="The company owning the others, when the group has one. It must be a member of the group.")
    currency_id = fields.Many2one(
        'res.currency', string="Group Currency", required=True, tracking=True,
        default=lambda self: self.env.company.currency_id,
        help="The currency of the consolidated reports: the balances of every company are translated into it.")
    member_ids = fields.One2many('om.consolidation.member', 'group_id', string="Members", copy=True)
    member_company_ids = fields.Many2many(
        'res.company', string="Member Companies", compute='_compute_member_company_ids')
    account_ids = fields.One2many('om.consolidation.account', 'group_id', string="Group Chart", copy=True)
    mapping_ids = fields.One2many('om.consolidation.mapping', 'group_id', string="Account Mapping", copy=True)
    period_ids = fields.One2many('om.consolidation.period', 'group_id', string="Periods")
    historical_rate_ids = fields.One2many(
        'om.consolidation.historical.rate', 'group_id', string="Historical Rates", copy=True)
    retained_earnings_account_id = fields.Many2one(
        'om.consolidation.account', string="Retained Earnings", domain="[('group_id', '=', id), ('kind', '=', 'equity')]",
        help="The group account the income and expense of the periods before the consolidated period go to.")
    translation_account_id = fields.Many2one(
        'om.consolidation.account', string="Translation Reserve", domain="[('group_id', '=', id), ('kind', '=', 'equity')]",
        help="The group account the differences of the currency translation go to, company by company.")
    difference_account_id = fields.Many2one(
        'om.consolidation.account', string="Elimination Differences", domain="[('group_id', '=', id)]",
        help="The group account an elimination that does not balance goes to: when the books of two companies "
             "do not agree on what they owe each other or sold to each other.")
    period_count = fields.Integer(compute='_compute_period_count')
    note = fields.Html(string="Notes")

    @api.depends('member_ids.company_id')
    def _compute_member_company_ids(self):
        for group in self:
            group.member_company_ids = group.member_ids.company_id

    def _compute_period_count(self):
        counts = dict(self.env['om.consolidation.period']._read_group(
            [('group_id', 'in', self.ids)], ['group_id'], ['__count']))
        for group in self:
            group.period_count = counts.get(group, 0)

    @api.constrains('parent_company_id', 'member_ids')
    def _check_parent_company(self):
        for group in self:
            if group.parent_company_id and group.parent_company_id not in group.member_ids.company_id:
                raise ValidationError(self.env._(
                    "The parent company %(company)s must be a member of the group %(group)s.",
                    company=group.parent_company_id.name, group=group.name))

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def _om_check_member_access(self):
        """Refuse a user who may not see every company of the group: the consolidated figures are made
        of the books of all of them."""
        for group in self:
            # the names of the companies the user may not read
            missing = group.sudo().member_ids.company_id - self.env.user.company_ids.sudo()
            if missing:
                raise AccessError(self.env._(
                    "The consolidation group %(group)s needs access to all its companies. You have no access "
                    "to: %(companies)s.", group=group.name, companies=', '.join(missing.mapped('name'))))

    def _om_rate_company(self):
        """The company whose currency rates translate the balances."""
        self.ensure_one()
        return self.parent_company_id or self.company_id

    # ------------------------------------------------------------------
    # Group chart and mapping
    # ------------------------------------------------------------------

    def action_load_default_chart(self):
        """Fill an empty group chart with a standard chart mapped by account type."""
        self.ensure_one()
        if self.account_ids:
            raise UserError(self.env._("The group already has a chart of accounts."))
        Account = self.env['om.consolidation.account']
        Mapping = self.env['om.consolidation.mapping']
        accounts = {}
        for sequence, (code, name, kind, elimination, account_types) in enumerate(DEFAULT_CHART):
            accounts[code] = Account.create({
                'group_id': self.id, 'code': code, 'name': str(name), 'kind': kind, 'elimination': elimination,
            })
            for account_type in account_types:
                Mapping.create({'group_id': self.id, 'sequence': sequence + 1, 'method': 'type',
                                'account_type': account_type, 'group_account_id': accounts[code].id})
        self.write({
            'retained_earnings_account_id': accounts['3200'].id,
            'translation_account_id': accounts['3300'].id,
            'difference_account_id': accounts['5900'].id,
        })
        return True

    def _om_company_accounts(self, company):
        """The accounts of ``company``, archived ones included."""
        return self.env['account.account'].with_company(company).with_context(active_test=False).search(
            [('company_ids', 'parent_of', company.id), ('account_type', '!=', 'off_balance')])

    def _om_account_map(self, company):
        """{account id: group account} of the accounts of ``company`` that are mapped."""
        self.ensure_one()
        rules = self.mapping_ids.filtered(
            lambda rule: not rule.company_id or rule.company_id == company
        ).sorted(lambda rule: (METHOD_PRIORITY[rule.method], rule.sequence, rule.id))
        result = {}
        for account in self._om_company_accounts(company):
            code = account.with_company(company).code or ''
            for rule in rules:
                if rule._om_matches(account, code):
                    result[account.id] = rule.group_account_id
                    break
        return result

    def _om_unmapped(self, date_to, date_from=False):
        """[(company, account, balance)] of the accounts with a balance (or a movement of the period, for
        income and expense) that no mapping rule maps to the group chart."""
        self.ensure_one()
        result = []
        MoveLine = self.env['account.move.line'].with_context(allowed_company_ids=self.member_ids.company_id.ids)
        for company in self.member_ids.company_id:
            mapped = self._om_account_map(company)
            domain = Domain([('company_id', '=', company.id), ('parent_state', '=', 'posted'),
                             ('date', '<=', date_to), ('account_id.account_type', '!=', 'off_balance')])
            if mapped:
                domain &= Domain('account_id', 'not in', list(mapped))
            if date_from:
                # income and expense before the period go to the retained earnings, mapped or not
                domain &= Domain('account_id.include_initial_balance', '=', True) | Domain('date', '>=', date_from)
            for account, balance in MoveLine._read_group(domain, ['account_id'], ['balance:sum']):
                if not company.currency_id.is_zero(balance):
                    result.append((company, account, balance))
        return result

    def action_check_mapping(self):
        """The accounts with a balance that are not mapped, at the end of the last period or today."""
        self.ensure_one()
        self._om_check_member_access()
        period = self.period_ids.sorted('date_to', reverse=True)[:1]
        date_to = period.date_to or fields.Date.context_today(self)
        return self.env['om.consolidation.unmapped']._om_open(self, date_to, period.date_from)

    def action_open_periods(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_account_consolidation.action_om_consolidation_period')
        action['domain'] = [('group_id', '=', self.id)]
        action['context'] = {'default_group_id': self.id}
        return action


class OmConsolidationMember(models.Model):
    _name = 'om.consolidation.member'
    _description = 'Consolidation Group Member'
    _order = 'sequence, id'

    group_id = fields.Many2one('om.consolidation.group', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', string="Company", required=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string="Currency")
    ownership = fields.Float(
        string="Ownership (%)", default=100.0, digits=(5, 2),
        help="The share of the company the group owns. The consolidation is a full consolidation: the "
             "companies are added in full.")

    _om_company_uniq = models.Constraint(
        'UNIQUE(group_id, company_id)', "A company is a member of a group once.")
    _om_ownership_range = models.Constraint(
        'CHECK(ownership >= 0 AND ownership <= 100)', "The ownership is between 0 and 100%.")


class OmConsolidationAccount(models.Model):
    """An account of the group chart: what the consolidated reports show."""
    _name = 'om.consolidation.account'
    _description = 'Group Account'
    _order = 'code, id'
    _rec_names_search = ['code', 'name']

    group_id = fields.Many2one('om.consolidation.group', required=True, ondelete='cascade', index=True)
    code = fields.Char(required=True)
    name = fields.Char(required=True, translate=True)
    kind = fields.Selection(
        ACCOUNT_KINDS, string="Type", required=True, default='asset',
        help="Where the account shows: assets, liabilities and equity in the balance sheet, income and "
             "expense in the profit and loss.")
    rate_type = fields.Selection(
        RATE_TYPES, string="Translation", compute='_compute_rate_type', store=True, readonly=False, precompute=True, required=True,
        help="The rate the balances are translated at: assets and liabilities at the closing rate, income and "
             "expense at the average rate of the period, equity at the historical rate.")
    elimination = fields.Selection(
        ELIMINATIONS, string="Elimination", required=True, default='none',
        help="Inter-company balances and sales and purchases: the journal items whose partner is another "
             "company of the group are eliminated. Dividends: the movements of the period are eliminated.")
    mapping_ids = fields.One2many('om.consolidation.mapping', 'group_account_id', string="Mapping")

    _om_code_uniq = models.Constraint('UNIQUE(group_id, code)', "The code of a group account is unique in the group.")

    @api.depends('kind')
    def _compute_rate_type(self):
        for account in self:
            if account.kind in ('asset', 'liability'):
                account.rate_type = 'closing'
            elif account.kind == 'equity':
                account.rate_type = 'historical'
            else:
                account.rate_type = 'average'

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for account in self:
            account.display_name = '%s %s' % (account.code or '', account.name or '')


class OmConsolidationMapping(models.Model):
    """How accounts of the companies map to a group account: one by one, by a range of codes or by
    their type. The accounts named one by one come first, then the code ranges, then the types."""
    _name = 'om.consolidation.mapping'
    _description = 'Consolidation Account Mapping'
    _order = 'sequence, id'

    group_id = fields.Many2one('om.consolidation.group', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company', string="Company",
        help="The company whose accounts the rule maps. Empty: every company of the group.")
    method = fields.Selection(MAPPING_METHODS, string="Map By", required=True, default='range')
    account_ids = fields.Many2many(
        'account.account', string="Accounts", context={'active_test': False},
        domain="[('account_type', '!=', 'off_balance')]")
    code_from = fields.Char(string="From Code")
    code_to = fields.Char(string="To Code")
    account_type = fields.Selection(
        selection=lambda self: self.env['account.account']._fields['account_type'].selection, string="Account Type")
    group_account_id = fields.Many2one(
        'om.consolidation.account', string="Group Account", required=True, ondelete='cascade',
        domain="[('group_id', '=', group_id)]")

    @api.constrains('method', 'account_ids', 'code_from', 'code_to', 'account_type')
    def _check_rule(self):
        for rule in self:
            if rule.method == 'account' and not rule.account_ids:
                raise ValidationError(self.env._("Choose the accounts of the mapping to %s.",
                                                 rule.group_account_id.display_name))
            if rule.method == 'range' and not (rule.code_from and rule.code_to):
                raise ValidationError(self.env._("Give the first and the last code of the mapping to %s.",
                                                 rule.group_account_id.display_name))
            if rule.method == 'range' and rule.code_from > rule.code_to:
                raise ValidationError(self.env._("The first code comes before the last one (%(start)s - %(end)s).",
                                                 start=rule.code_from, end=rule.code_to))
            if rule.method == 'type' and not rule.account_type:
                raise ValidationError(self.env._("Choose the account type of the mapping to %s.",
                                                 rule.group_account_id.display_name))

    @api.constrains('group_account_id', 'group_id')
    def _check_group_account(self):
        for rule in self:
            if rule.group_account_id.group_id != rule.group_id:
                raise ValidationError(self.env._("A mapping maps to an account of its own group."))

    def _om_matches(self, account, code):
        """Whether the rule maps ``account`` (whose code in the company is ``code``). A code range
        compares the codes from their start: 4000 - 4999 takes 400000 to 499999."""
        self.ensure_one()
        if self.method == 'account':
            return account in self.account_ids
        if self.method == 'type':
            return account.account_type == self.account_type
        if not code:
            return False
        return self.code_from <= code and code[:len(self.code_to)] <= self.code_to


class OmConsolidationHistoricalRate(models.Model):
    """The rate the equity of a company is translated at: the rate of the day the capital was paid in,
    for example. Without one, the equity is carried over from the previous period of the group."""
    _name = 'om.consolidation.historical.rate'
    _description = 'Consolidation Historical Rate'
    _order = 'company_id, group_account_id'

    group_id = fields.Many2one('om.consolidation.group', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string="Company", required=True)
    group_account_id = fields.Many2one(
        'om.consolidation.account', string="Group Account",
        domain="[('group_id', '=', group_id), ('rate_type', '=', 'historical')]",
        help="Empty: every account of the company translated at the historical rate.")
    rate = fields.Float(
        string="Rate", digits=0, required=True,
        help="The group currency for one unit of the currency of the company.")

    @api.constrains('group_id', 'company_id', 'group_account_id')
    def _check_unique(self):
        for rate in self:
            if self.search_count([('id', '!=', rate.id), ('group_id', '=', rate.group_id.id),
                                  ('company_id', '=', rate.company_id.id),
                                  ('group_account_id', '=', rate.group_account_id.id)]):
                raise ValidationError(self.env._("A company has one historical rate per group account."))

    _om_rate_positive = models.Constraint('CHECK(rate > 0)', "A rate is above zero.")


class OmConsolidationUnmapped(models.TransientModel):
    """An account with a balance that maps to no account of the group chart."""
    _name = 'om.consolidation.unmapped'
    _description = 'Unmapped Account'
    _order = 'company_id, code'

    group_id = fields.Many2one('om.consolidation.group', readonly=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True)
    account_id = fields.Many2one('account.account', string="Account", readonly=True)
    code = fields.Char(readonly=True)
    account_type = fields.Selection(related='account_id.account_type')
    currency_id = fields.Many2one(related='company_id.currency_id')
    balance = fields.Monetary(readonly=True)

    @api.model
    def _om_open(self, group, date_to, date_from=False):
        unmapped = group._om_unmapped(date_to, date_from)
        if not unmapped:
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'title': self.env._("Mapping complete"),
                           'message': self.env._("Every account with a balance maps to the group chart.")},
            }
        records = self.create([{
            'group_id': group.id, 'company_id': company.id, 'account_id': account.id,
            'code': account.with_company(company).code, 'balance': balance,
        } for company, account, balance in unmapped])
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Unmapped Accounts"),
            'res_model': self._name,
            'view_mode': 'list',
            'domain': [('id', 'in', records.ids)],
            'context': {'create': False},
            'target': 'new',
        }
