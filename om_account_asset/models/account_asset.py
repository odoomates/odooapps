import calendar
import math
from collections import defaultdict
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
from markupsafe import Markup

DEPRECIATION_METHODS = [
    ('linear', 'Linear'),
    ('degressive', 'Degressive'),
    ('degressive_then_linear', 'Degressive then Linear'),
]
TIME_METHODS = [
    ('number', 'Number of Entries'),
    ('end', 'Ending Date'),
    ('rate', 'Depreciation Rate'),
]
METHOD_HELP = (
    "Choose the method to use to compute the amount of depreciation entries.\n"
    "  * Linear: Calculated on basis of: Gross Value / Number of Depreciations\n"
    "  * Degressive: Calculated on basis of: Residual Value * Degressive Factor\n"
    "  * Degressive then Linear: Degressive, switching to linear as soon as spreading "
    "the residual value over the remaining life gives a higher amount"
)
TIME_METHOD_HELP = (
    "Choose the method to use to compute the dates and number of entries.\n"
    "  * Number of Entries: Fix the number of entries and the time between 2 depreciations.\n"
    "  * Ending Date: Choose the time between 2 depreciations and the date the depreciations won't go beyond.\n"
    "  * Depreciation Rate: Depreciate a fixed percentage of the depreciable value every year."
)
# fields changing the depreciation board of an asset
BOARD_FIELDS = {
    'value', 'salvage_value', 'opening_depreciation', 'date', 'method', 'method_number',
    'method_period', 'method_end', 'method_rate', 'method_progress_factor', 'method_time', 'prorata',
    'date_first_depreciation', 'first_depreciation_manual_date', 'category_id', 'currency_id',
}
# a partial disposal removes a share of the depreciation from the board
BOARD_ENTRY_TYPES = ('depreciation', 'revaluation', 'partial_disposal')


def _days_in_month(day):
    return calendar.monthrange(day.year, day.month)[1]


def _month_fraction(start, end):
    """ Months elapsed from the end of day `start` to the end of day `end`, the days of
    an incomplete month counting as a fraction of that month (e.g. Feb 28th to Mar 16th
    is 16/31). """
    return ((end.year - start.year) * 12 + end.month - start.month
            + end.day / _days_in_month(end) - start.day / _days_in_month(start))


def _add_month_fraction(start, months):
    """ Inverse of `_month_fraction`: the day ending `months` months after the end of `start`. """
    whole = math.floor(months + 1e-9)
    base = start + relativedelta(months=whole)
    position = start.day / _days_in_month(start) + months - whole
    if position > 1 + 1e-9:
        base = (base + relativedelta(months=1)).replace(day=1)
        position -= 1
    day = round(position * _days_in_month(base))
    if day < 1:
        return base.replace(day=1) - timedelta(days=1)
    return base.replace(day=min(day, _days_in_month(base)))


class AccountAssetCategory(models.Model):
    _name = 'account.asset.category'
    _description = 'Asset category'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']

    exclude_types = ['asset_receivable', 'asset_cash', 'liability_payable',
                     'liability_credit_card', 'equity', 'equity_unaffected']

    active = fields.Boolean(default=True)
    name = fields.Char(required=True, index=True, string="Name")
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    account_asset_id = fields.Many2one(
        'account.account', string='Asset Account',
        required=True,
        domain=[('account_type', 'not in', exclude_types)],
        help="Account used to record the purchase of the asset at its original price."
    )
    account_depreciation_id = fields.Many2one(
        'account.account', string='Depreciation Entries: Asset Account',
        required=True,
        domain=[('account_type', 'not in', exclude_types)],
        help="Account used in the depreciation entries, to decrease the asset value."
    )
    account_depreciation_expense_id = fields.Many2one(
        'account.account', string='Depreciation Entries: Expense Account',
        required=True,
        domain=[('account_type', 'not in', exclude_types)],
        help="Account used in the periodical entries "
             "to record a part of the asset as expense."
    )
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company
    )
    method = fields.Selection(
        DEPRECIATION_METHODS, string='Computation Method', required=True, default='linear',
        help=METHOD_HELP,
    )
    method_number = fields.Integer(
        string='Number of Depreciations', default=5,
        help="The number of depreciations needed to depreciate your asset"
    )
    method_period = fields.Integer(
        string='Period Length', default=1,
        help="State here the time between 2 depreciations, in months", required=True
    )
    method_progress_factor = fields.Float(
        'Degressive Factor', default=0.3
    )
    method_time = fields.Selection(
        TIME_METHODS, string='Time Method', required=True, default='number',
        help=TIME_METHOD_HELP,
    )
    method_end = fields.Date('Ending date')
    method_rate = fields.Float(
        string='Depreciation Rate (%)',
        help="Percentage of the depreciable value depreciated every year."
    )
    prorata = fields.Boolean(
        string='Prorata Temporis',
        help='Indicates that the first depreciation entry for this asset have to be done from the '
             'purchase date instead of the first of January'
    )
    open_asset = fields.Boolean(
        string='Auto-Confirm Assets',
        help="Check this if you want to automatically confirm the assets "
             "of this category when created by invoices."
    )
    create_from_bill = fields.Boolean(
        string='Assets from Bills on the Asset Account',
        help="Vendor bill lines booked on the asset account of this category get this category, "
             "so that their assets are created when the bill is posted."
    )
    asset_per_unit = fields.Boolean(
        string='One Asset per Unit',
        help="A bill line of several units creates one asset for each unit instead of one for the line."
    )
    type = fields.Selection(
        [('sale', 'Sale: Revenue Recognition'), ('purchase', 'Purchase: Asset')],
        required=True, index=True, default='purchase'
    )
    date_first_depreciation = fields.Selection([
        ('last_day_period', 'Based on Last Day of Purchase Period'),
        ('manual', 'Manual (Defaulted on Purchase Date)')],
        string='Depreciation Dates', default='manual', required=True,
        help='The way to compute the date of the first depreciation.\n'
             '  * Based on last day of purchase period: The depreciation dates will'
             ' be based on the last day of the purchase month or the purchase'
             ' year (depending on the periodicity of the depreciations).\n'
             '  * Based on purchase date: The depreciation dates will be based on the purchase date.')

    asset_count = fields.Integer(compute='_compute_asset_count', string='# Assets')

    def _compute_asset_count(self):
        counts = dict(self.env['account.asset.asset']._read_group(
            [('category_id', 'in', self.ids)], ['category_id'], ['__count']))
        for category in self:
            category.asset_count = counts.get(category, 0)

    def action_view_assets(self):
        self.ensure_one()
        assets = self.env['account.asset.asset'].search([('category_id', '=', self.id)])
        action = assets._get_assets_action(
            _('Assets of %s', self.name) if self.type == 'purchase' else _('Deferred Revenues of %s', self.name))
        action['context'] = {'default_category_id': self.id}
        return action

    @api.constrains('method_time', 'method_rate')
    def _check_method_rate(self):
        for category in self:
            if category.method_time == 'rate' and float_compare(category.method_rate, 0.0, precision_digits=2) <= 0:
                raise ValidationError(_('The depreciation rate of "%s" must be greater than 0.', category.name))

    @api.constrains('type', 'account_asset_id', 'account_depreciation_id', 'account_depreciation_expense_id')
    def _check_depreciation_expense_account(self):
        for category in self.filtered(lambda c: c.type == 'purchase'):
            if category.account_depreciation_expense_id in (
                    category.account_asset_id | category.account_depreciation_id):
                raise ValidationError(_(
                    'The depreciation expense account of the asset category "%(category)s" must differ from its '
                    'asset account and its accumulated depreciation account: booked on the same account, the '
                    'depreciation would cancel itself and never reach the profit and loss.',
                    category=category.name))

    @api.constrains('create_from_bill', 'account_asset_id', 'company_id', 'type', 'active')
    def _check_create_from_bill(self):
        for category in self.filtered(lambda c: c.create_from_bill and c.active):
            if category.type != 'purchase':
                raise ValidationError(
                    _('Only asset categories can create their assets from the bills on their account.'))
            if category._get_bill_categories(category.account_asset_id, category.company_id) != category:
                raise ValidationError(_(
                    'Another category already creates its assets from the bills on the account %s.',
                    category.account_asset_id.display_name))

    @api.model
    def _get_bill_categories(self, account, company):
        """ Categories giving their assets to the vendor bill lines booked on `account`. """
        return self.search([
            ('create_from_bill', '=', True),
            ('type', '=', 'purchase'),
            ('account_asset_id', '=', account.id),
            ('company_id', '=', company.id),
        ])

    @api.onchange('account_asset_id')
    def onchange_account_asset(self):
        if self.type == "purchase":
            self.account_depreciation_id = self.account_asset_id
        elif self.type == "sale":
            self.account_depreciation_expense_id = self.account_asset_id

    @api.onchange('type')
    def onchange_type(self):
        if self.type == 'sale':
            self.prorata = True
            self.method_period = 1
        else:
            self.method_period = 12


class AccountAssetAsset(models.Model):
    _name = 'account.asset.asset'
    _description = 'Asset/Revenue Recognition'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']

    entry_count = fields.Integer(compute='_entry_count', string='# Asset Entries')
    name = fields.Char(string='Asset Name', required=True)
    code = fields.Char(string='Reference', size=32)
    value = fields.Monetary(string='Gross Value', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.user.company_id.currency_id.id
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    note = fields.Text()
    category_id = fields.Many2one(
        'account.asset.category', string='Category',
        required=True, change_default=True
    )
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Running'),
        ('paused', 'Paused'),
        ('close', 'Close'),
        ('cancelled', 'Cancelled')],
        'Status', required=True, copy=False, default='draft',
        help="When an asset is created, the status is 'Draft'.\n"
             "If the asset is confirmed, the status goes in 'Running': its depreciation entries "
             "are created and each one is posted on its date.\n"
             "A running asset can be put 'Paused': no depreciation is computed until it is resumed.\n"
             "The asset is closed once its last depreciation is posted, or when it is sold or disposed.\n"
             "A cancelled asset had its journal entries removed or reversed.")
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string='Partner')
    method = fields.Selection(
        DEPRECIATION_METHODS, string='Computation Method', required=True, default='linear',
        help=METHOD_HELP,
    )
    method_number = fields.Integer(string='Number of Depreciations', default=5,
                                   help="The number of depreciations needed to depreciate your asset")
    method_period = fields.Integer(
        string='Number of Months in a Period', required=True, default=12,
        help="The amount of time between two depreciations, in months"
    )
    method_end = fields.Date(string='Ending Date')
    method_rate = fields.Float(
        string='Depreciation Rate (%)',
        help="Percentage of the depreciable value depreciated every year."
    )
    method_progress_factor = fields.Float(
        string='Degressive Factor', default=0.3
    )
    value_residual = fields.Monetary(
        compute='_amount_residual', string='Residual Value',
        help="Depreciable value left once the posted depreciation entries are deducted."
    )
    book_value = fields.Monetary(
        compute='_amount_residual', string='Book Value',
        help="Residual value plus salvage value: what the asset is still worth in the books."
    )
    method_time = fields.Selection(
        TIME_METHODS, string='Time Method', required=True, default='number',
        help=TIME_METHOD_HELP,
    )
    prorata = fields.Boolean(
        string='Prorata Temporis',
        help='Indicates that the first depreciation entry for this asset'
             ' have to be done from the asset date (purchase date) '
             'instead of the first January / Start date of fiscal year'
    )
    depreciation_move_ids = fields.One2many(
        'account.move', 'depreciation_asset_id', string='Depreciation Board',
        domain=[('asset_entry_type', 'in', BOARD_ENTRY_TYPES)],
    )
    salvage_value = fields.Monetary(
        string='Salvage Value',
        help="It is the amount you plan to have that you cannot depreciate."
    )
    opening_depreciation = fields.Monetary(
        string='Opening Depreciation',
        help="Depreciation already booked before the asset was recorded in Odoo, e.g. in a previous "
             "software. The board is computed from the asset date and this amount is deducted from "
             "the first depreciations, so no journal entry is created for it."
    )
    invoice_id = fields.Many2one('account.move', string='Invoice', copy=False)
    type = fields.Selection(related="category_id.type", string='Type', required=True)
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    date_first_depreciation = fields.Selection([
        ('last_day_period', 'Based on Last Day of Purchase Period'),
        ('manual', 'Manual')],
        string='Depreciation Dates', default='manual',
        required=True,
        help='The way to compute the date of the first depreciation.\n'
             '  * Based on last day of purchase period: The depreciation'
             ' dates will be based on the last day of the purchase month or the '
             'purchase year (depending on the periodicity of the depreciations).\n'
             '  * Based on purchase date: The depreciation dates will be based on the purchase date.\n')
    first_depreciation_manual_date = fields.Date(
        string='First Depreciation Date',
        help='Note that this date does not alter the computation of the first '
             'journal entry in case of prorata temporis assets. It simply changes its accounting date'
    )
    pause_date = fields.Date(string='Paused Since', copy=False, readonly=True)
    paused_months = fields.Float(
        copy=False, readonly=True, digits=(16, 6),
        help="Technical field: months the asset was on hold, added to its life.")
    depreciation_restart_date = fields.Date(
        copy=False, readonly=True,
        help="Technical field: date the depreciation restarted after the last pause.")
    disposal_date = fields.Date(string='Disposal Date', copy=False, readonly=True)
    disposal_move_id = fields.Many2one('account.move', string='Disposal Entry', copy=False, readonly=True)
    disposal_result = fields.Monetary(
        string='Disposal Gain/Loss', copy=False, readonly=True,
        help="Selling price minus book value at the disposal date, in company currency."
    )
    parent_id = fields.Many2one(
        'account.asset.asset', string='Parent Asset', index='btree_not_null', copy=False, readonly=True,
        help="Set on value increases: the asset whose value was increased by a re-evaluation."
    )
    children_ids = fields.One2many('account.asset.asset', 'parent_id', string='Value Increases')
    increase_count = fields.Integer(compute='_compute_gross_increase_count')
    increase_value = fields.Monetary(
        compute='_compute_gross_increase_count', string='Value Increase',
        help="Value added to the asset by its value increases.")
    account_asset_id = fields.Many2one(related='category_id.account_asset_id', string='Fixed Asset Account')
    account_depreciation_id = fields.Many2one(
        related='category_id.account_depreciation_id', string='Accumulated Depreciation Account')
    account_depreciation_expense_id = fields.Many2one(
        related='category_id.account_depreciation_expense_id', string='Depreciation Expense Account')
    journal_id = fields.Many2one(related='category_id.journal_id', string='Journal')
    increase_move_id = fields.Many2one(
        'account.move', string='Value Increase Entry', copy=False, readonly=True,
    )

    def unlink(self):
        for asset in self:
            if asset.state in ['open', 'paused', 'close']:
                raise UserError(_('You cannot delete a document that is in %s state.') % (asset.state,))
            if asset._get_board_moves().filtered(lambda m: m.state == 'posted'):
                raise UserError(_('You cannot delete a document that contains posted entries.'))
        self.depreciation_move_ids.with_context(om_asset_board_update=True).unlink()
        return super().unlink()

    # -------------------------------------------------------------------------
    # BOARD COMPUTATION
    # -------------------------------------------------------------------------

    def _get_first_period_end(self):
        """ Date of the first depreciation of the asset. """
        self.ensure_one()
        first_date = self.date
        if self.date_first_depreciation == 'last_day_period':
            first_date = first_date + relativedelta(day=31)
            if self.method_period == 12:
                first_date = first_date + relativedelta(month=int(self.company_id.fiscalyear_last_month),
                                                        day=int(self.company_id.fiscalyear_last_day))
                if first_date < self.date:
                    first_date = first_date + relativedelta(years=1)
        elif self.first_depreciation_manual_date:
            first_date = self.first_depreciation_manual_date
        return first_date

    def _get_period_end(self, first_end, periods):
        """ Date of the depreciation `periods` periods after `first_end`. """
        period_end = first_end + relativedelta(months=periods * self.method_period)
        if first_end.day == _days_in_month(first_end):
            period_end = period_end + relativedelta(day=31)
        return period_end

    def _get_period_end_after(self, cursor):
        """ First depreciation date of the calendar of the asset strictly after `cursor`. """
        first_end = self._get_first_period_end()
        if cursor < first_end:
            return first_end
        periods = max(int(_month_fraction(first_end, cursor) // self.method_period) - 1, 0)
        period_end = self._get_period_end(first_end, periods)
        while period_end <= cursor:
            periods += 1
            period_end = self._get_period_end(first_end, periods)
        return period_end

    def _get_lifetime_start(self):
        """ Day before the depreciation starts: the purchase date with prorata temporis,
        the start of the first period otherwise. """
        self.ensure_one()
        if self.prorata:
            return self.date - timedelta(days=1)
        first_end = self._get_first_period_end()
        return self._get_period_end(first_end, -1)

    def _get_lifetime_months(self):
        """ Length of the depreciation in months, time on hold included. """
        self.ensure_one()
        if self.method_period <= 0:
            raise UserError(_('The period length of "%s" must be greater than 0.', self.name))
        start = self._get_lifetime_start()
        if self.method_time == 'rate':
            if float_compare(self.method_rate, 0.0, precision_digits=2) <= 0:
                raise UserError(_('Set a depreciation rate on "%s".', self.name))
            months = 1200.0 / self.method_rate
        elif self.method_time == 'end':
            if not self.method_end:
                raise UserError(_('Set an ending date on "%s" to compute its depreciation board.', self.name))
            if self.prorata:
                months = _month_fraction(start, self.method_end)
            else:
                first_end = self._get_first_period_end()
                periods = 0
                while self._get_period_end(first_end, periods + 1) <= self.method_end:
                    periods += 1
                months = (periods + 1) * self.method_period
        else:
            months = self.method_number * self.method_period
        return max(months, 0.0) + self.paused_months

    def _get_lifetime_end(self):
        return _add_month_fraction(self._get_lifetime_start(), self._get_lifetime_months())

    def _get_board_moves(self):
        """ Entries of the depreciation board, i.e. changing the value left to depreciate. """
        return self.depreciation_move_ids.filtered(lambda m: m.asset_entry_type in BOARD_ENTRY_TYPES)

    def _get_board_cursor(self, moves):
        """ Last day covered by the depreciation of `moves`. """
        cursor = self._get_lifetime_start()
        dated_moves = moves.filtered(lambda m: m.state != 'cancel' and not m.reversed_entry_id)
        if dated_moves:
            cursor = max(cursor, max(dated_moves.mapped('date')))
        if self.depreciation_restart_date:
            cursor = max(cursor, self.depreciation_restart_date - timedelta(days=1))
        return cursor

    def _compute_board_values(self, residual_amount, cursor, imported_amount):
        """ Depreciations of `residual_amount` from the day after `cursor` to the end of the life.

        :param imported_amount: depreciation booked before the import, deducted from the first depreciations
        :return: list of ``(period_start, period_end, amount)``
        """
        self.ensure_one()
        currency = self.currency_id
        start = self._get_lifetime_start()
        remaining_months = self._get_lifetime_months() - _month_fraction(start, cursor)
        depreciable_value = self.value - self.salvage_value
        values = []
        for _dummy in range(5000):
            if currency.is_zero(residual_amount):
                break
            period_end = self._get_period_end_after(cursor)
            months = _month_fraction(cursor, period_end)
            is_last = remaining_months <= months + 1e-6
            if self.method_time == 'rate':
                amount = depreciable_value * self.method_rate / 100.0 * months / 12.0
            elif is_last:
                amount = residual_amount
            elif self.method == 'linear':
                amount = residual_amount * months / remaining_months
            elif self.method == 'degressive':
                amount = residual_amount * self.method_progress_factor * months / self.method_period
            else:
                amount = max(residual_amount * self.method_progress_factor * months / self.method_period,
                             residual_amount * months / remaining_months)
            if is_last or abs(amount) > abs(residual_amount):
                amount = residual_amount
            amount = currency.round(amount)
            residual_amount -= amount

            entry_amount = amount
            if imported_amount:
                if abs(imported_amount) >= abs(entry_amount):
                    imported_amount -= entry_amount
                    entry_amount = 0.0
                else:
                    entry_amount = currency.round(entry_amount - imported_amount)
                    imported_amount = 0.0
            if not currency.is_zero(entry_amount):
                values.append((cursor, period_end, entry_amount))
            remaining_months -= months
            cursor = period_end
        return values

    def _recompute_board(self, keep_until=None):
        """ Replace the draft depreciation entries by a new board.

        :param keep_until: keep the draft entries dated on or before this date
        """
        self.ensure_one()
        drafts = self._get_board_moves().filtered(lambda m: m.state == 'draft')
        if keep_until:
            drafts = drafts.filtered(lambda m: m.date > keep_until)
        drafts.with_context(om_asset_board_update=True).unlink()
        if self.state not in ('draft', 'open'):
            return self.env['account.move']

        kept_moves = self._get_board_moves().filtered(lambda m: m.state != 'cancel')
        has_depreciation = bool(kept_moves.filtered(lambda m: not m.reversed_entry_id))
        imported_amount = 0.0 if has_depreciation else self.opening_depreciation
        residual_amount = (self.value - self.salvage_value - self.opening_depreciation
                           - sum(kept_moves.mapped('asset_depreciation_amount')) + imported_amount)
        cursor = self._get_board_cursor(kept_moves)
        board_values = self._compute_board_values(residual_amount, cursor, imported_amount)
        moves = self.env['account.move'].create([
            self._prepare_depreciation_move_vals(amount, period_start, period_end)
            for period_start, period_end, amount in board_values
        ])
        if self.state == 'open':
            # past entries are posted now, the others on their date
            moves._post(soft=True)
        return moves

    def compute_depreciation_board(self):
        """ Preview the board of draft assets, recompute the rest of the board of running ones. """
        for asset in self:
            asset._recompute_board()
        return True

    def _prepare_depreciation_move_vals(self, amount, period_start, move_date, entry_type='depreciation'):
        self.ensure_one()
        category = self.category_id
        company = self.company_id
        company_currency = company.currency_id
        balance = self.currency_id._convert(amount, company_currency, company, move_date)
        name = _('%s: Depreciation', self.name) if entry_type == 'depreciation' else _('%s: Re-evaluation', self.name)
        line_vals = {
            'name': name,
            'partner_id': self.partner_id.id,
            'analytic_distribution': self.analytic_distribution,
            'currency_id': self.currency_id.id,
        }
        return {
            'ref': name,
            'date': move_date,
            'journal_id': category.journal_id.id,
            'move_type': 'entry',
            'partner_id': self.partner_id.id,
            'depreciation_asset_id': self.id,
            'asset_entry_type': entry_type,
            'asset_depreciation_amount': amount,
            'asset_period_start': period_start,
            'line_ids': [
                Command.create({
                    **line_vals,
                    'account_id': category.account_depreciation_id.id,
                    'balance': -balance,
                    'amount_currency': -amount,
                }),
                Command.create({
                    **line_vals,
                    'account_id': category.account_depreciation_expense_id.id,
                    'balance': balance,
                    'amount_currency': amount,
                }),
            ],
        }

    def _get_residual_at(self, at_date):
        """ Value left to depreciate once the entries dated on or before `at_date` are posted. """
        self.ensure_one()
        moves = self._get_board_moves().filtered(lambda m: m.state != 'cancel' and m.date <= at_date)
        return (self.value - self.salvage_value - self.opening_depreciation
                - sum(moves.mapped('asset_depreciation_amount')))

    def _get_partial_depreciation(self, operation_date):
        """ :return: the draft entry running over `operation_date` and the part of its amount
                     depreciated up to that date """
        self.ensure_one()
        next_move = self._get_board_moves().filtered(
            lambda m: m.state == 'draft' and m.date > operation_date
        ).sorted(lambda m: (m.date, m.id))[:1]
        if not next_move:
            return next_move, 0.0
        period_start = next_move.asset_period_start or self._get_lifetime_start()
        period_months = _month_fraction(period_start, next_move.date)
        elapsed_months = _month_fraction(period_start, operation_date)
        ratio = 1.0 if period_months <= 0 else min(max(elapsed_months / period_months, 0.0), 1.0)
        return next_move, self.currency_id.round(next_move.asset_depreciation_amount * ratio)

    def _depreciate_until(self, operation_date):
        """ Depreciate the running period up to `operation_date` and remove the later entries.
        The entries due up to that date are posted. """
        self.ensure_one()
        due_moves = self._get_board_moves().filtered(lambda m: m.state == 'draft' and m.date <= operation_date)
        due_moves._post(soft=True)
        next_move, amount = self._get_partial_depreciation(operation_date)
        period_start = next_move.asset_period_start or self._get_lifetime_start()
        self._get_board_moves().filtered(
            lambda m: m.state == 'draft' and m.date > operation_date
        ).with_context(om_asset_board_update=True).unlink()
        if next_move and not self.currency_id.is_zero(amount):
            partial_move = self.env['account.move'].create(
                self._prepare_depreciation_move_vals(amount, period_start, operation_date))
            partial_move._post(soft=True)

    # -------------------------------------------------------------------------
    # LIFECYCLE
    # -------------------------------------------------------------------------

    def validate(self):
        self.write({'state': 'open'})
        fields = [
            'method',
            'method_number',
            'method_period',
            'method_end',
            'method_rate',
            'method_progress_factor',
            'method_time',
            'salvage_value',
            'opening_depreciation',
            'invoice_id',
        ]
        ref_tracked_fields = self.env['account.asset.asset'].fields_get(fields)
        for asset in self:
            preview_moves = asset._get_board_moves().filtered(lambda m: m.state == 'draft')
            if preview_moves:
                # keep the amounts that may have been changed on the preview
                preview_moves._post(soft=True)
            else:
                asset._recompute_board()
            tracked_fields = ref_tracked_fields.copy()
            if asset.method == 'linear':
                del(tracked_fields['method_progress_factor'])
            if asset.method_time != 'end':
                del(tracked_fields['method_end'])
            if asset.method_time != 'number':
                del(tracked_fields['method_number'])
            if asset.method_time != 'rate':
                del(tracked_fields['method_rate'])
            dummy, tracking_values = asset._mail_track(tracked_fields, dict.fromkeys(fields))
            asset.message_post(subject=_('Asset created'), message_type='tracking', tracking_values=tracking_values)

    def _check_lock_date(self, operation_date):
        for asset in self:
            lock_date = asset.company_id._get_user_fiscal_lock_date(asset.category_id.journal_id)
            if lock_date and operation_date <= lock_date:
                raise UserError(_(
                    'The operation date %(date)s on "%(asset)s" is on or before the lock date %(lock_date)s.',
                    date=operation_date, asset=asset.name, lock_date=lock_date,
                ))

    def _close_if_depreciated(self):
        for asset in self.filtered(lambda a: a.state == 'open'):
            if asset.currency_id.is_zero(asset.value_residual) \
                    and not asset._get_board_moves().filtered(lambda m: m.state == 'draft'):
                asset.write({'state': 'close'})
                asset.message_post(body=_("Document closed."))

    def _with_running_increases(self, states):
        """ The assets and their value increases in `states`, which follow them when paused,
        resumed or disposed of. """
        return self | self.children_ids.filtered(lambda increase: increase.state in states)

    @api.model
    def _links_markup(self, records):
        return Markup(' / ').join([record._get_html_link() for record in records])

    def pause(self, on_date, note=None):
        """ Stop depreciating on `on_date`: the running period is depreciated up to that day
        and the scheduled entries are removed until the asset is resumed. """
        for asset in self._with_running_increases(('open',)):
            if asset.state != 'open':
                raise UserError(_('Only running assets can be paused.'))
            if on_date < asset.date - timedelta(days=1):
                raise UserError(_('"%s" cannot be paused before its acquisition.', asset.name))
            asset._check_lock_date(on_date)
            asset._depreciate_until(on_date)
            if asset.state == 'open':  # else the last partial entry fully depreciated it
                asset.write({'state': 'paused', 'pause_date': on_date})
                asset.message_post(body=_('Depreciation paused on %(date)s. %(note)s', date=on_date, note=note or ''))

    def resume(self, on_date, note=None):
        """ Depreciate again from `on_date`, the paused time lengthens the life of the asset. """
        for asset in self._with_running_increases(('paused',)):
            if asset.state != 'paused':
                raise UserError(_('Only paused assets can be resumed.'))
            if on_date <= asset.pause_date:
                raise UserError(_('"%(asset)s" was paused on %(date)s, resume it after that day.',
                                  asset=asset.name, date=asset.pause_date))
            asset._check_lock_date(on_date)
            paused_months = _month_fraction(asset.pause_date, on_date - timedelta(days=1))
            asset.write({
                'state': 'open',
                'pause_date': False,
                'paused_months': asset.paused_months + paused_months,
                'depreciation_restart_date': on_date,
            })
            asset._recompute_board()
            asset.message_post(body=_('Depreciation resumed on %(date)s. %(note)s', date=on_date, note=note or ''))

    def _create_value_increase(self, increase_date, amount, counterpart_account):
        """ Create and confirm the asset carrying a value increase of `self`, depreciated
        until the end of the life of `self`. """
        self.ensure_one()
        category = self.category_id
        company = self.company_id
        balance = self.currency_id._convert(amount, company.currency_id, company, increase_date)
        name = _('%s: value increase', self.name)
        child = self.create({
            'name': name,
            'code': self.code,
            'category_id': category.id,
            'value': amount,
            'salvage_value': 0.0,
            'currency_id': self.currency_id.id,
            'company_id': company.id,
            'partner_id': self.partner_id.id,
            # the parent depreciates the day of the increase, the increase starts the day after
            'date': increase_date + timedelta(days=1),
            'parent_id': self.id,
            'method': 'linear' if self.method_time == 'rate' else self.method,
            'method_progress_factor': self.method_progress_factor,
            'method_period': self.method_period,
            'method_time': 'end',
            'method_end': self._get_lifetime_end(),
            'prorata': True,
            'date_first_depreciation': 'manual',
            'first_depreciation_manual_date': self._get_period_end_after(increase_date),
            'account_analytic_id': self.account_analytic_id.id,
            'analytic_distribution': self.analytic_distribution,
        })
        move = self.env['account.move'].create({
            'ref': name,
            'date': increase_date,
            'journal_id': category.journal_id.id,
            'move_type': 'entry',
            'depreciation_asset_id': child.id,
            'asset_entry_type': 'value_increase',
            'line_ids': [
                Command.create({
                    'name': name,
                    'account_id': category.account_asset_id.id,
                    'balance': balance,
                    'partner_id': self.partner_id.id,
                    'analytic_distribution': self.analytic_distribution,
                }),
                Command.create({
                    'name': name,
                    'account_id': counterpart_account.id,
                    'balance': -balance,
                    'partner_id': self.partner_id.id,
                }),
            ],
        })
        move._post(soft=False)
        child.increase_move_id = move
        child.validate()
        self.message_post(body=_('Value increase recorded in %s', child._get_html_link()))
        return child

    def set_to_close(self, sale_lines=None, disposal_date=None, note=None):
        """ Remove the asset and its value increases from the books.

        :param sale_lines: customer invoice lines when the asset is sold, disposed of otherwise
        :param disposal_date: today when not given
        :return: action opening the disposal entries
        """
        self.ensure_one()
        sale_lines = sale_lines or self.env['account.move.line']
        disposal_date = disposal_date or fields.Date.context_today(self)
        if self.state not in ('open', 'paused'):
            raise UserError(_('Only running or paused assets can be sold or disposed of.'))
        assets = self._with_running_increases(('open', 'paused'))
        if sale_lines and assets != self:
            raise UserError(_('"%s" has running value increases: dispose of them before selling it.', self.name))

        disposal_moves = self.env['account.move']
        for asset in assets:
            disposal_moves |= asset._dispose(disposal_date, sale_lines if asset == self else sale_lines.browse(), note)
        if not disposal_moves:
            return self.open_entries()
        if len(disposal_moves) == 1:
            return self._open_record_action(disposal_moves)
        return {
            'name': _('Disposal Entries'),
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'domain': [('id', 'in', disposal_moves.ids)],
        }

    def _get_disposal_balances(self, disposal_date, sale_lines, disposed=None):
        """ Balance per account of the entry removing the asset from the books, in company currency:
        the gross value leaves the asset account, the accumulated depreciation is cancelled, the sale
        price leaves the income accounts of the invoice and the rest is a gain or a loss.

        :param disposed: partial disposal, amounts in the currency of the asset removed from the books:
                         value, opening (depreciation before import) and depreciation (posted)
        :return: (list of (account, balance), book value, sale price)
        """
        company = self.company_id
        currency = company.currency_id
        category = self.category_id

        def to_company_currency(amount, at_date):
            return currency.round(self.currency_id._convert(amount, currency, company, at_date))

        if disposed:
            gross_value, accumulated = self._get_disposed_company_amounts(
                disposed['value'], disposed['opening'], disposed['depreciation'], disposal_date)
        else:
            gross_value = to_company_currency(self.value, self.date)
            accumulated = to_company_currency(self.opening_depreciation, self.date)
            for move in self._get_board_moves().filtered(lambda m: m.state == 'posted'):
                accumulated += to_company_currency(move.asset_depreciation_amount, move.date)
        sale_price_by_account = defaultdict(float)
        for line in sale_lines:
            sale_price_by_account[line.account_id] -= line.balance
        sale_price = currency.round(sum(sale_price_by_account.values()))
        book_value = currency.round(gross_value - accumulated)
        result = currency.round(sale_price - book_value)
        result_account = company.asset_gain_account_id if result > 0 else company.asset_loss_account_id
        if not currency.is_zero(result) and not result_account:
            raise UserError(_('Set the gain and loss accounts for assets in the Accounting settings.'))

        balances = [(category.account_asset_id, -gross_value), (category.account_depreciation_id, accumulated)]
        balances += [(account, currency.round(amount)) for account, amount in sale_price_by_account.items()]
        balances.append((result_account, -result))
        return [(account, balance) for account, balance in balances
                if account and not currency.is_zero(balance)], book_value, sale_price

    def _dispose_partially(self, disposal_date, share, sale_lines=None, note=None):
        """ Sell or dispose of `share` (between 0 and 1) of the asset: the running period is depreciated up to
        `disposal_date`, the same share of the gross value, salvage value and depreciation leaves the books with a
        posted entry booking the gain or the loss, and the rest of the asset depreciates on.

        :return: the partial disposal entry
        """
        self.ensure_one()
        currency = self.currency_id
        sale_lines = sale_lines or self.env['account.move.line']
        if self.state not in ('open', 'paused'):
            raise UserError(_('Only running or paused assets can be sold or disposed of.'))
        if not 0.0 < share < 1.0:
            raise UserError(_('The share of the asset disposed of must be between 0 and 100%.'))
        if self.children_ids.filtered(lambda increase: increase.state in ('open', 'paused')):
            raise UserError(_('"%s" has running value increases: sell or dispose of the whole asset.', self.name))
        if disposal_date < self.date - timedelta(days=1):
            raise UserError(_('"%s" cannot be disposed of before its acquisition.', self.name))
        if disposal_date > fields.Date.context_today(self):
            raise UserError(_('A partial disposal cannot be recorded in the future.'))
        self._check_lock_date(disposal_date)
        if self.state == 'open':
            self._depreciate_until(disposal_date)

        posted_moves = self._get_board_moves().filtered(lambda m: m.state == 'posted')
        disposed = {
            'value': currency.round(self.value * share),
            'salvage': currency.round(self.salvage_value * share),
            'opening': currency.round(self.opening_depreciation * share),
            'depreciation': currency.round(sum(posted_moves.mapped('asset_depreciation_amount')) * share),
        }
        balances, book_value, sale_price = self._get_disposal_balances(disposal_date, sale_lines, disposed=disposed)
        self.write({
            'value': self.value - disposed['value'],
            'salvage_value': self.salvage_value - disposed['salvage'],
            'opening_depreciation': self.opening_depreciation - disposed['opening'],
        })
        label = _('%(asset)s: Partial Sale (%(share)s%%)', asset=self.name, share=round(share * 100, 2)) if sale_lines \
            else _('%(asset)s: Partial Disposal (%(share)s%%)', asset=self.name, share=round(share * 100, 2))
        move = self.env['account.move'].create({
            'ref': label,
            'date': disposal_date,
            'journal_id': self.category_id.journal_id.id,
            'move_type': 'entry',
            'depreciation_asset_id': self.id,
            'asset_entry_type': 'partial_disposal',
            'asset_depreciation_amount': -disposed['depreciation'],
            'asset_period_start': disposal_date,
            'asset_disposed_value': disposed['value'],
            'asset_disposed_salvage': disposed['salvage'],
            'asset_disposed_opening': disposed['opening'],
            'line_ids': [
                Command.create({
                    'name': label,
                    'account_id': account.id,
                    'balance': balance,
                    'analytic_distribution': self.analytic_distribution,
                })
                for account, balance in balances
            ],
        })
        move._post(soft=False)
        if self.state == 'open':
            self._recompute_board(keep_until=disposal_date)
        company_currency = self.company_id.currency_id
        result = company_currency.round(sale_price - book_value)
        body = _('%(share)s%% sold on %(date)s (%(invoices)s), %(entry)s. Gain or loss: %(result)s. %(note)s',
                 share=round(share * 100, 2), date=disposal_date, invoices=self._links_markup(sale_lines.move_id),
                 entry=move._get_html_link(), result=result, note=note or '') if sale_lines else \
            _('%(share)s%% disposed of on %(date)s, %(entry)s. Loss: %(result)s. %(note)s',
              share=round(share * 100, 2), date=disposal_date, entry=move._get_html_link(), result=-result,
              note=note or '')
        self.message_post(body=body)
        return move

    def _get_disposed_company_amounts(self, value, opening, depreciation, disposal_date):
        """ Gross value and accumulated depreciation removed by a partial disposal, in company currency. """
        company = self.company_id
        currency = company.currency_id

        def to_company_currency(amount, at_date):
            return currency.round(self.currency_id._convert(amount, currency, company, at_date))

        return (to_company_currency(value, self.date),
                to_company_currency(opening, self.date) + to_company_currency(depreciation, disposal_date))

    def _dispose(self, disposal_date, sale_lines, note=None):
        """ Depreciate up to `disposal_date` and create the draft entry removing the asset from the books. """
        self.ensure_one()
        if disposal_date < self.date - timedelta(days=1):
            raise UserError(_('"%s" cannot be disposed of before its acquisition.', self.name))
        self._check_lock_date(disposal_date)
        if self.state == 'open':
            self._depreciate_until(disposal_date)
        self._get_board_moves().filtered(lambda m: m.state == 'draft').with_context(om_asset_board_update=True).unlink()

        balances, book_value, sale_price = self._get_disposal_balances(disposal_date, sale_lines)
        label = _('%s: Sale', self.name) if sale_lines else _('%s: Disposal', self.name)
        disposal_move = self.env['account.move']
        if balances:
            disposal_move = disposal_move.create({
                'ref': label,
                'date': disposal_date,
                'journal_id': self.category_id.journal_id.id,
                'move_type': 'entry',
                'depreciation_asset_id': self.id,
                'asset_entry_type': 'sale' if sale_lines else 'disposal',
                'line_ids': [
                    Command.create({
                        'name': label,
                        'account_id': account.id,
                        'balance': balance,
                        'analytic_distribution': self.analytic_distribution,
                    })
                    for account, balance in balances
                ],
            })
        self.write({
            'state': 'close',
            'pause_date': False,
            'disposal_date': disposal_date,
            'disposal_move_id': disposal_move.id,
            'disposal_result': sale_price - book_value,
        })
        if sale_lines:
            body = _('Sold on %(date)s (%(invoices)s). %(note)s', date=disposal_date,
                     invoices=self._links_markup(sale_lines.move_id), note=note or '')
        else:
            body = _('Disposed of on %(date)s. %(note)s', date=disposal_date, note=note or '')
        self.message_post(body=body)
        return disposal_move

    def set_to_cancelled(self):
        """ Cancel the asset: its journal entries are deleted, or reversed when they cannot be. """
        for asset in self | self.children_ids.filtered(lambda a: a.state not in ('draft', 'cancelled')):
            if asset.state == 'cancelled':
                continue
            if asset.state == 'draft':
                raise UserError(_('Delete the draft asset "%s" instead of cancelling it.', asset.name))
            moves = (asset.depreciation_move_ids | asset.disposal_move_id | asset.increase_move_id).filtered(
                lambda m: m.state != 'cancel' and not m.reversed_entry_id and not m.reversal_move_ids)
            reversals = moves.with_context(om_asset_board_update=True)._unlink_or_reverse()
            asset.write({
                'state': 'cancelled',
                'pause_date': False,
                'disposal_date': False,
                'disposal_move_id': False,
            })
            if reversals:
                asset.message_post(body=_('Cancelled, the entries that could not be deleted are reversed by %s',
                                          self._links_markup(reversals)))
            else:
                asset.message_post(body=_('Cancelled, its entries are deleted.'))

    def set_to_draft(self):
        for asset in self:
            if asset._get_board_moves().filtered(lambda m: m.state == 'posted'):
                raise UserError(_('"%s" has posted depreciation entries, cancel it instead.', asset.name))
        self.depreciation_move_ids.with_context(om_asset_board_update=True).unlink()
        self.write({'state': 'draft', 'pause_date': False, 'paused_months': 0.0, 'depreciation_restart_date': False})

    @api.depends('value', 'salvage_value', 'opening_depreciation',
                 'depreciation_move_ids.state', 'depreciation_move_ids.asset_depreciation_amount')
    def _amount_residual(self):
        for rec in self:
            posted_moves = rec._get_board_moves().filtered(lambda m: m.state == 'posted')
            rec.value_residual = (rec.value - rec.salvage_value - rec.opening_depreciation
                                  - sum(posted_moves.mapped('asset_depreciation_amount')))
            rec.book_value = rec.value_residual + rec.salvage_value

    @api.depends('children_ids.value', 'children_ids.state')
    def _compute_gross_increase_count(self):
        for asset in self:
            increases = asset.children_ids.filtered(lambda a: a.state != 'cancelled')
            asset.increase_count = len(asset.children_ids)
            asset.increase_value = sum(increases.mapped('value'))

    @api.onchange('company_id')
    def onchange_company_id(self):
        self.currency_id = self.company_id.currency_id.id

    @api.onchange('date_first_depreciation')
    def onchange_date_first_depreciation(self):
        for record in self:
            if record.date_first_depreciation == 'manual':
                record.first_depreciation_manual_date = record.date

    @api.depends('depreciation_move_ids.state', 'disposal_move_id', 'increase_move_id')
    def _entry_count(self):
        for asset in self:
            moves = asset.depreciation_move_ids | asset.disposal_move_id | asset.increase_move_id
            asset.entry_count = len(moves.filtered(lambda m: m.state == 'posted'))

    @api.constrains('method_time', 'method_end', 'method_rate')
    def _check_time_method(self):
        for asset in self:
            if asset.method_time == 'end' and not asset.method_end:
                raise ValidationError(_('Set the ending date of "%s".', asset.name))
            if asset.method_time == 'rate' and float_compare(asset.method_rate, 0.0, precision_digits=2) <= 0:
                raise ValidationError(_('The depreciation rate of "%s" must be greater than 0.', asset.name))

    @api.constrains('value', 'salvage_value', 'opening_depreciation')
    def _check_already_depreciated_amount(self):
        for asset in self:
            if float_compare(asset.opening_depreciation, 0.0, precision_rounding=asset.currency_id.rounding) < 0 \
                    or float_compare(asset.opening_depreciation, asset.value - asset.salvage_value,
                                     precision_rounding=asset.currency_id.rounding) > 0:
                raise ValidationError(_(
                    'The depreciation before import of "%s" must be between 0 and its depreciable value.', asset.name))

    @api.onchange('category_id')
    def onchange_category_id(self):
        vals = self.onchange_category_id_values(self.category_id.id)
        # We cannot use 'write' on an object that doesn't exist yet
        if vals:
            for k, v in vals['value'].items():
                setattr(self, k, v)

    def onchange_category_id_values(self, category_id):
        if category_id:
            category = self.env['account.asset.category'].browse(category_id)
            return {
                'value': {
                    'method': category.method,
                    'method_number': category.method_number,
                    'method_time': category.method_time,
                    'method_period': category.method_period,
                    'method_progress_factor': category.method_progress_factor,
                    'method_end': category.method_end,
                    'method_rate': category.method_rate,
                    'prorata': category.prorata,
                    'date_first_depreciation': category.date_first_depreciation,
                    'account_analytic_id': category.account_analytic_id.id,
                    'analytic_distribution': category.analytic_distribution,
                }
            }

    def copy_data(self, default=None):
        if default is None:
            default = {}
        default['name'] = self.name + _(' (copy)')
        return super().copy_data(default)

    @api.model_create_multi
    def create(self, vals_list):
        return super(AccountAssetAsset, self.with_context(mail_create_nolog=True)).create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'analytic_distribution' in vals:
            self._get_board_moves().filtered(
                lambda m: m.state == 'draft').line_ids.analytic_distribution = vals['analytic_distribution']
        if BOARD_FIELDS & set(vals):
            # refresh the preview of draft assets, running boards change through the asset actions
            for asset in self.filtered(lambda a: a.state == 'draft' and a.depreciation_move_ids):
                asset._recompute_board()
        return res

    def open_entries(self):
        moves = self.depreciation_move_ids | self.disposal_move_id | self.increase_move_id
        # same list as the Journal Entries menu, with its "Posted" filter set as the button counts posted entries
        return {
            'name': _('Journal Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'views': [(self.env.ref('account.view_move_tree').id, 'list'), (False, 'form')],
            'search_view_id': [self.env.ref('account.view_account_move_filter').id, 'search'],
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False, 'view_no_maturity': True},
        }

    def _open_record_action(self, record):
        return {
            'res_model': record._name,
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': record.id,
        }

    def _get_assets_action(self, name):
        """ :return: the action showing these assets, the form when there is only one """
        action = self.env['ir.actions.act_window']._for_xml_id('om_account_asset.action_account_asset_asset_form')
        action.update({
            'name': name,
            'domain': [('id', 'in', self.ids)],
            'context': {'create': False},
        })
        if len(self) == 1:
            action.update({'view_mode': 'form', 'views': [(False, 'form')], 'res_id': self.id})
        return action

    def open_invoice(self):
        self.ensure_one()
        return self._open_record_action(self.invoice_id)

    def open_parent_asset(self):
        self.ensure_one()
        return self._open_record_action(self.parent_id)

    def open_disposal_move(self):
        self.ensure_one()
        return self._open_record_action(self.disposal_move_id)

    def action_view_increases(self):
        self.ensure_one()
        action = {
            'name': _('Value Increases'),
            'res_model': 'account.asset.asset',
            'type': 'ir.actions.act_window',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.children_ids.ids)],
            'context': {'create': False},
        }
        if len(self.children_ids) == 1:
            action.update({'view_mode': 'form', 'res_id': self.children_ids.id})
        return action
