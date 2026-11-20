import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, formatLang
from markupsafe import Markup

DEPRECIATION_METHODS = [
    ('linear', 'Linear'),
    ('degressive', 'Degressive'),
    ('none', 'No Depreciation'),
]
METHOD_HELP = (
    "Choose the method to use to compute the amount of depreciation lines.\n"
    "  * Linear: Calculated on basis of: Gross Value / Number of Depreciations\n"
    "  * Degressive: Calculated on basis of: Residual Value * Degressive Factor\n"
    "  * No Depreciation: the asset keeps its value, e.g. land or an asset under construction, until its "
    "depreciation is activated"
)
PRORATA_COMPUTATION_TYPES = [
    ('constant_periods', 'Constant Periods'),
    ('daily_computation', 'Based on Days per Period'),
]
PRORATA_COMPUTATION_HELP = (
    "How a period is weighted in the depreciation:\n"
    "  * Constant Periods: every period counts the same.\n"
    "  * Based on Days per Period: every day counts the same, so a period of 31 days depreciates more than one "
    "of 28 days."
)

# only these fields change the depreciation board: writing anything else (a note, a
# partner, active, ...) must not throw away the unposted lines of the board
BOARD_FIELDS = {
    'value', 'salvage_value', 'date', 'currency_id', 'method', 'method_number',
    'method_period', 'method_end', 'method_time', 'method_progress_factor',
    'prorata', 'date_first_depreciation', 'first_depreciation_manual_date', 'prorata_computation_type',
}


class AccountAssetCategory(models.Model):
    _name = 'account.asset.category'
    _description = 'Asset category'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']

    exclude_types = ['asset_receivable', 'asset_cash', 'liability_payable',
                     'liability_credit_card', 'equity', 'equity_unaffected']

    active = fields.Boolean(default=True)
    name = fields.Char(required=True, index=True, string="Asset Type")
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    account_asset_id = fields.Many2one(
        'account.account', string='Asset Account',
        required=True,
        domain=[('account_type', 'not in', exclude_types), ('deprecated', '=', False)],
        help="Account used to record the purchase of the asset at its original price."
    )
    account_depreciation_id = fields.Many2one(
        'account.account', string='Depreciation Entries: Asset Account',
        required=True,
        domain=[('account_type', 'not in', exclude_types), ('deprecated', '=', False)],
        help="Account used in the depreciation entries, to decrease the asset value."
    )
    account_depreciation_expense_id = fields.Many2one(
        'account.account', string='Depreciation Entries: Expense Account',
        required=True,
        domain=[('account_type', 'not in', exclude_types), ('deprecated', '=', False)],
        help="Account used in the periodical entries "
             "to record a part of the asset as expense."
    )
    account_asset_gain_id = fields.Many2one(
        'account.account', string='Disposal Entries: Gain Account',
        domain=[('account_type', 'not in', exclude_types)],
        help="Account used by the disposal entry to record a sale above the book value "
             "of the asset."
    )
    account_asset_loss_id = fields.Many2one(
        'account.account', string='Disposal Entries: Loss Account',
        domain=[('account_type', 'not in', exclude_types)],
        help="Account used by the disposal entry to record the book value an asset still "
             "carried when it left the books."
    )
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company
    )
    method = fields.Selection(
        DEPRECIATION_METHODS, string='Computation Method', required=True, default='linear', help=METHOD_HELP
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
        'Degressive Factor', default=0.3,
        help='Yearly rate of the degressive method: 0.3 depreciates 30% of the value left at the start of each year, '
             'spread over the periods of the year.'
    )
    method_time = fields.Selection(
        [('number', 'Number of Entries'), ('end', 'Ending Date')],
        string='Time Method', required=True, default='number',
        help="Choose the method to use to compute the dates and number of entries.\n"
           "  * Number of Entries: Fix the number of entries and the time between 2 depreciations.\n"
           "  * Ending Date: Choose the time between 2 depreciations and the date the depreciations won't go beyond."
    )
    method_end = fields.Date('Ending date')
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
    group_entries = fields.Boolean(
        string='Group Journal Entries',
        help="Check this if you want to group the generated entries by categories."
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
    prorata_computation_type = fields.Selection(
        PRORATA_COMPUTATION_TYPES, string='Computation', required=True, default='constant_periods',
        help=PRORATA_COMPUTATION_HELP)
    asset_properties_definition = fields.PropertiesDefinition(string='Asset Properties')
    salvage_value_pct = fields.Float(
        string='Salvage Value (%)',
        help='Share of the gross value of a new asset of this category that is not depreciated.')

    @api.constrains('salvage_value_pct')
    def _check_salvage_value_pct(self):
        for category in self:
            if not 0.0 <= category.salvage_value_pct < 100.0:
                raise ValidationError(_('The salvage value of "%s" must be between 0 and 100%%.', category.name))

    def _get_salvage_value(self, value):
        """ The salvage value of a new asset of this category worth `value`. """
        self.ensure_one()
        return self.company_id.currency_id.round(value * self.salvage_value_pct / 100.0)

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

    @api.onchange('method_time')
    def _onchange_method_time(self):
        if self.method_time != 'number':
            self.prorata = False


class AccountAssetAsset(models.Model):
    _name = 'account.asset.asset'
    _description = 'Asset/Revenue Recognition'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']

    entry_count = fields.Integer(compute='_entry_count', string='# Asset Entries')
    name = fields.Char(string='Asset Name', required=True)
    code = fields.Char(string='Reference')
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
    state = fields.Selection([('draft', 'Draft'), ('open', 'Running'), ('close', 'Close')],
                             'Status', required=True, copy=False, default='draft',
        help="When an asset is created, the status is 'Draft'.\n"
            "If the asset is confirmed, the status goes in 'Running' and the depreciation "
             "lines can be posted in the accounting.\n"
            "You can manually close an asset when the depreciation is over. If the last line"
             " of depreciation is posted, the asset automatically goes in that status.")
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string='Partner')
    method = fields.Selection(
        DEPRECIATION_METHODS, string='Computation Method', required=True, default='linear', help=METHOD_HELP
    )
    method_number = fields.Integer(string='Number of Depreciations', default=5,
                                   help="The number of depreciations needed to depreciate your asset")
    method_period = fields.Integer(
        string='Number of Months in a Period', required=True, default=12,
        help="The amount of time between two depreciations, in months"
    )
    method_end = fields.Date(string='Ending Date')
    method_progress_factor = fields.Float(
        string='Degressive Factor', default=0.3,
        help='Yearly rate of the degressive method: 0.3 depreciates 30% of the value left at the start of each year, '
             'spread over the periods of the year.'
    )
    value_residual = fields.Monetary(compute='_amount_residual', string='Residual Value')
    method_time = fields.Selection(
        [('number', 'Number of Entries'), ('end', 'Ending Date')],
        string='Time Method', required=True, default='number',
        help="Choose the method to use to compute the dates and number of entries.\n"
             "  * Number of Entries: Fix the number of entries and the time between 2 depreciations.\n"
             "  * Ending Date: Choose the time between 2 depreciations and the date the depreciations won't go beyond."
    )
    prorata = fields.Boolean(
        string='Prorata Temporis',
        help='Indicates that the first depreciation entry for this asset'
             ' have to be done from the asset date (purchase date) '
             'instead of the first January / Start date of fiscal year'
    )
    depreciation_line_ids = fields.One2many(
        'account.asset.depreciation.line', 'asset_id', string='Depreciation Lines'
    )
    salvage_value = fields.Monetary(
        string='Salvage Value',
        help="It is the amount you plan to have that you cannot depreciate."
    )
    invoice_id = fields.Many2one('account.move', string='Invoice', copy=False)
    original_move_line_ids = fields.Many2many(
        'account.move.line', 'om_asset_move_line_rel', 'asset_id', 'line_id', string='Journal Items', copy=False,
        readonly=True, help='The journal items the asset was created from.')
    refunded_asset_id = fields.Many2one(
        'account.asset.asset', string='Refund Of', copy=False, readonly=True, index='btree_not_null',
        help='Set on the negative asset of a vendor refund: the asset of the bill that was refunded.')
    refund_ids = fields.One2many('account.asset.asset', 'refunded_asset_id', string='Refunds')
    group_id = fields.Many2one('account.asset.group', string='Asset Group', tracking=True, index='btree_not_null',
                               check_company=True)
    asset_properties = fields.Properties(string='Properties', definition='category_id.asset_properties_definition',
                                         copy=True)
    prorata_computation_type = fields.Selection(
        PRORATA_COMPUTATION_TYPES, string='Computation', required=True, default='constant_periods',
        help=PRORATA_COMPUTATION_HELP)
    book_value = fields.Monetary(
        compute='_compute_book_value', string='Book Value',
        help="Gross value of the asset less the depreciation already recorded. A fully "
             "depreciated asset is still worth its salvage value.")
    disposal_date = fields.Date(string='Disposal Date', readonly=True, copy=False)
    disposal_move_id = fields.Many2one(
        'account.move', string='Disposal Entry', readonly=True, copy=False)
    disposal_result = fields.Monetary(
        string='Gain / Loss on Disposal', readonly=True, copy=False)
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

    def unlink(self):
        for asset in self:
            if asset.state in ['open', 'close']:
                raise UserError(_('You cannot delete a document that is in %s state.') % (asset.state,))
            for depreciation_line in asset.depreciation_line_ids:
                if depreciation_line.move_id:
                    raise UserError(_('You cannot delete a document that contains posted entries.'))
        return super(AccountAssetAsset, self).unlink()

    @api.model
    def _cron_generate_entries(self):
        self.compute_generated_entries(datetime.today())

    @api.model
    def compute_generated_entries(self, date, asset_type=None):
        # Entries generated : one by grouped category and one by asset from ungrouped category
        created_move_ids = []
        type_domain = []
        if asset_type:
            type_domain = [('type', '=', asset_type)]

        ungrouped_assets = self.env['account.asset.asset'].search(type_domain + [('state', '=', 'open'), ('category_id.group_entries', '=', False)])
        created_move_ids += ungrouped_assets._compute_entries(date, group_entries=False)

        for grouped_category in self.env['account.asset.category'].search(type_domain + [('group_entries', '=', True)]):
            assets = self.env['account.asset.asset'].search([('state', '=', 'open'), ('category_id', '=', grouped_category.id)])
            created_move_ids += assets._compute_entries(date, group_entries=True)
        return created_move_ids

    def _compute_board_amount(self, sequence, residual_amount, amount_to_depr,
                              undone_dotation_number, posted_depreciation_line_ids,
                              total_days, depreciation_date, year_residual=None, days=None):
        """ :param year_residual: for a degressive asset depreciated by periods shorter than a year, the residual
        value at the start of the year of the life of the asset the line belongs to
        :param days: with the computation based on days, (days of the period of the line, days left in the life of
        the asset from the start of that period) """
        amount = 0
        if sequence == undone_dotation_number:
            amount = residual_amount
        elif days and self.method == 'linear':
            # every day weighs the same: the share of the period in the life left
            period_days, remaining_days = days
            amount = residual_amount * period_days / remaining_days if remaining_days > 0 else residual_amount
        elif days and self.method == 'degressive' and self.method_period < 12 and year_residual is not None:
            # the share of the yearly rate of the days of the period, a year counting 365 days
            amount = year_residual * self.method_progress_factor * days[0] / 365.0
        else:
            if self.method == 'linear':
                # amount_to_depr is the *residual* value, i.e. already net of the posted
                # lines, so it must always be spread over the *remaining* periods.
                amount = amount_to_depr / (undone_dotation_number - len(posted_depreciation_line_ids))
                if self.prorata and not posted_depreciation_line_ids:
                    amount = amount_to_depr / self.method_number
                    if sequence == 1:
                        date = self.date
                        if self.method_period % 12 != 0:
                            month_days = calendar.monthrange(date.year, date.month)[1]
                            days = month_days - date.day + 1
                            amount = (amount_to_depr / self.method_number) / month_days * days
                        else:
                            days = (self.company_id.compute_fiscalyear_dates(date)['date_to'] - date).days + 1
                            amount = (amount_to_depr / self.method_number) / total_days * days
            elif self.method == 'degressive':
                # the degressive factor is a yearly rate: a period shorter than a year depreciates its share of the
                # value left at the start of the year
                if self.method_period < 12 and year_residual is not None:
                    period_amount = year_residual * self.method_progress_factor * self.method_period / 12.0
                else:
                    period_amount = residual_amount * self.method_progress_factor
                amount = period_amount
                if self.prorata:
                    if sequence == 1:
                        date = self.date
                        if self.method_period % 12 != 0:
                            month_days = calendar.monthrange(date.year, date.month)[1]
                            days = month_days - date.day + 1
                            amount = period_amount / month_days * days
                        else:
                            days = (self.company_id.compute_fiscalyear_dates(date)['date_to'] - date).days + 1
                            amount = (residual_amount * self.method_progress_factor) / total_days * days
        return amount

    def _get_degressive_year(self, sequence):
        """ The year of the life of the asset of the depreciation line `sequence` (from 1): with the prorata
        temporis, the first line is a part of the first period. """
        self.ensure_one()
        return int((sequence - 1) * self.method_period // 12)

    def _get_degressive_year_start(self, sequence, residual_amount, posted_lines):
        """ The year of the life of the asset of the line `sequence`, the residual value at its start (the residual
        now plus the depreciation posted since the start of the year) and what the year may still depreciate.

        :return: (year, residual value at the start of the year, amount left for the year)
        """
        self.ensure_one()
        year = self._get_degressive_year(sequence)
        booked = sum(line.amount for line in posted_lines if self._get_degressive_year(line.sequence) == year)
        year_residual = residual_amount + booked
        return year, year_residual, year_residual * self.method_progress_factor - booked

    def _get_board_days(self, depreciation_date, month_day, posted_lines, undone_dotation_number):
        """ For the computation based on days: the days of the period of each line still to compute, and the days
        left in the life of the asset from the start of that period.

        :return: {sequence: (days of the period, days left)}
        """
        self.ensure_one()
        if posted_lines:
            period_start = posted_lines[-1].depreciation_date
        elif self.prorata:
            # the first period starts on the purchase date
            period_start = self.date - timedelta(days=1)
        else:
            period_start = depreciation_date - relativedelta(months=self.method_period)
        ends = []
        cursor = depreciation_date
        for _sequence in range(len(posted_lines), undone_dotation_number):
            ends.append(cursor)
            cursor = self._next_depreciation_date(cursor, month_day)
        if not ends:
            return {}
        life_end = ends[-1]
        result = {}
        for index, end in enumerate(ends):
            result[len(posted_lines) + index + 1] = ((end - period_start).days, (life_end - period_start).days)
            period_start = end
        return result

    def _compute_board_undone_dotation_nb(self, depreciation_date, total_days):
        undone_dotation_number = self.method_number
        if self.method_time == 'end':
            end_date = self.method_end
            undone_dotation_number = 0
            while depreciation_date <= end_date:
                depreciation_date = date(depreciation_date.year, depreciation_date.month,
                                         depreciation_date.day) + relativedelta(months=+self.method_period)
                undone_dotation_number += 1
        if self.prorata:
            undone_dotation_number += 1
        return undone_dotation_number

    def _next_depreciation_date(self, depreciation_date, month_day):
        """ Advance the board cursor by one period, keeping the day of the month. """
        depreciation_date = depreciation_date + relativedelta(months=+self.method_period)

        if month_day > 28 and self.date_first_depreciation == 'manual':
            max_day_in_month = calendar.monthrange(depreciation_date.year, depreciation_date.month)[1]
            depreciation_date = depreciation_date.replace(day=min(max_day_in_month, month_day))

        # datetime doesn't take into account that the number of days is not the same
        # for each month: without this, relativedelta clamps 31-Jan to 28-Feb and the
        # whole board then stays on the 28th (this must apply with prorata too)
        if self.method_period % 12 != 0 and self.date_first_depreciation == 'last_day_period':
            max_day_in_month = calendar.monthrange(depreciation_date.year, depreciation_date.month)[1]
            depreciation_date = depreciation_date.replace(day=max_day_in_month)

        return depreciation_date

    def compute_depreciation_board(self):
        self.ensure_one()

        posted_depreciation_line_ids = self.depreciation_line_ids.filtered(lambda x: x.move_check).sorted(key=lambda l: l.depreciation_date)
        unposted_depreciation_line_ids = self.depreciation_line_ids.filtered(lambda x: not x.move_check)

        # Remove old unposted depreciation lines. We cannot use unlink() with One2many field
        commands = [(2, line_id.id, False) for line_id in unposted_depreciation_line_ids]

        # an asset without depreciation keeps its value until its depreciation is activated
        if self.value_residual != 0.0 and self.method != 'none':
            amount_to_depr = residual_amount = self.value_residual

            # if we already have some previous validated entries, starting date is last entry + method period
            if posted_depreciation_line_ids and posted_depreciation_line_ids[-1].depreciation_date:
                last_depreciation_date = fields.Date.from_string(posted_depreciation_line_ids[-1].depreciation_date)
                depreciation_date = last_depreciation_date + relativedelta(months=+self.method_period)
            else:
                # depreciation_date computed from the purchase date
                depreciation_date = self.date
                if self.date_first_depreciation == 'last_day_period':
                    # depreciation_date = the last day of the month
                    depreciation_date = depreciation_date + relativedelta(day=31)
                    # ... or fiscalyear depending the number of period
                    if self.method_period == 12:
                        depreciation_date = depreciation_date + relativedelta(month=int(self.company_id.fiscalyear_last_month))
                        depreciation_date = depreciation_date + relativedelta(day=int(self.company_id.fiscalyear_last_day))
                        if depreciation_date < self.date:
                            depreciation_date = depreciation_date + relativedelta(years=1)
                elif self.first_depreciation_manual_date and self.first_depreciation_manual_date != self.date:
                    # depreciation_date set manually from the 'first_depreciation_manual_date' field
                    depreciation_date = self.first_depreciation_manual_date
            total_days = calendar.isleap(depreciation_date.year) and 366 or 365
            month_day = depreciation_date.day
            undone_dotation_number = self._compute_board_undone_dotation_nb(depreciation_date, total_days)
            if self.method_time == 'end':
                # the helper counts periods from the *next* depreciation date, so with
                # posted lines it returns the remaining count while the loop below
                # indexes over the whole board
                undone_dotation_number += len(posted_depreciation_line_ids)

            # a negative asset (a vendor refund) is depreciated the other way round
            sign = -1 if float_compare(residual_amount, 0.0, precision_rounding=self.currency_id.rounding) < 0 else 1
            daily_days = self._get_board_days(depreciation_date, month_day, posted_depreciation_line_ids,
                                              undone_dotation_number) \
                if self.prorata_computation_type == 'daily_computation' else {}
            # a degressive asset depreciated by periods shorter than a year: the residual value at the start of the
            # current year of its life, and what the year may still depreciate
            yearly = self.method == 'degressive' and self.method_period < 12
            year, year_residual, year_left = self._get_degressive_year_start(
                len(posted_depreciation_line_ids) + 1, residual_amount, posted_depreciation_line_ids)
            for x in range(len(posted_depreciation_line_ids), undone_dotation_number):
                sequence = x + 1
                if yearly and self._get_degressive_year(sequence) != year:
                    year = self._get_degressive_year(sequence)
                    year_residual = residual_amount
                    year_left = year_residual * self.method_progress_factor
                amount = self._compute_board_amount(sequence, residual_amount, amount_to_depr,
                                                    undone_dotation_number, posted_depreciation_line_ids,
                                                    total_days, depreciation_date,
                                                    year_residual=year_residual if yearly else None,
                                                    days=daily_days.get(sequence))
                if yearly and sequence != undone_dotation_number:
                    # nothing more once the share of the year is reached, e.g. an asset depreciated too much before,
                    # which then follows the method from the next year
                    amount = sign * max(min(sign * amount, sign * year_left), 0.0)
                amount = self.currency_id.round(amount)
                if yearly:
                    year_left -= amount
                if float_is_zero(amount, precision_rounding=self.currency_id.rounding):
                    # skip the line but still move on to the next period, otherwise the
                    # following lines would all be dated on the same day
                    depreciation_date = self._next_depreciation_date(depreciation_date, month_day)
                    continue
                residual_amount -= amount
                vals = {
                    'amount': amount,
                    'asset_id': self.id,
                    'sequence': sequence,
                    'name': (self.code or '') + '/' + str(sequence),
                    'remaining_value': residual_amount,
                    'depreciated_value': self.value - (self.salvage_value + residual_amount),
                    'depreciation_date': depreciation_date,
                }
                commands.append((0, False, vals))

                depreciation_date = self._next_depreciation_date(depreciation_date, month_day)

        self.write({'depreciation_line_ids': commands})

        return True

    def validate(self):
        self.write({'state': 'open'})
        fields = [
            'method',
            'method_number',
            'method_period',
            'method_end',
            'method_progress_factor',
            'method_time',
            'salvage_value',
            'invoice_id',
        ]
        ref_tracked_fields = self.env['account.asset.asset'].fields_get(fields)
        for asset in self:
            tracked_fields = ref_tracked_fields.copy()
            if asset.method in ('linear', 'none'):
                del(tracked_fields['method_progress_factor'])
            if asset.method_time != 'end':
                del(tracked_fields['method_end'])
            else:
                del(tracked_fields['method_number'])
            dummy, tracking_value_ids = asset._mail_track(tracked_fields, dict.fromkeys(fields))
            asset.message_post(subject=_('Asset created'), tracking_value_ids=tracking_value_ids)

    def _return_disposal_view(self, move_ids):
        name = _('Disposal Move')
        view_mode = 'form'
        if len(move_ids) > 1:
            name = _('Disposal Moves')
            view_mode = 'list,form'
        return {
            'name': name,
            'view_type': 'form',
            'view_mode': view_mode,
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'res_id': move_ids[0],
        }

    def _in_books(self):
        """ The assets still carried in the books: the running ones, and the ones closed by
        their last depreciation entry. A fully depreciated asset is only worth its salvage
        value, and it stays on the books until it is sold or disposed of, which is what
        `disposal_date` records. """
        return self.filtered(lambda asset: asset.state == 'open'
                             or (asset.state == 'close' and not asset.disposal_date))

    def _depreciate_until(self, disposal_date):
        """ Stop the depreciation on `disposal_date`: the entries due up to that day are
        posted, the ones scheduled after it are replaced by a single entry for the value
        left to depreciate. """
        self.ensure_one()
        lines = self.depreciation_line_ids.sorted(lambda line: (line.depreciation_date, line.id))
        due = lines.filtered(lambda line: not line.move_check and line.depreciation_date <= disposal_date)
        if due:
            due.create_move(post_move=True)
        scheduled = lines.filtered(lambda line: not line.move_check)
        residual = self.value_residual
        if not scheduled and self.currency_id.is_zero(residual):
            return
        old_values = {'method_end': self.method_end, 'method_number': self.method_number}
        commands = [(2, line.id, False) for line in scheduled]
        sequence = len(self.depreciation_line_ids) - len(scheduled) + 1
        if not self.currency_id.is_zero(residual):
            commands.append((0, False, {
                'amount': residual,
                'asset_id': self.id,
                'sequence': sequence,
                'name': (self.code or '') + '/' + str(sequence),
                'remaining_value': 0.0,
                # the asset is completely depreciated
                'depreciated_value': self.value - self.salvage_value,
                'depreciation_date': disposal_date,
            }))
        self.write({'depreciation_line_ids': commands,
                    'method_end': disposal_date,
                    'method_number': sequence})
        tracked_fields = self.env['account.asset.asset'].fields_get(['method_number', 'method_end'])
        changes, tracking_value_ids = self._mail_track(tracked_fields, old_values)
        if changes:
            self.message_post(subject=_('Depreciation stopped on the disposal of the asset.'),
                              tracking_value_ids=tracking_value_ids)
        last = self.depreciation_line_ids.filtered(lambda line: not line.move_check)
        if last:
            last.create_move(post_move=True)

    def _disposal_balances(self, disposal_date, sale_lines):
        """ Balance per account of the entry removing the asset from the books, in company
        currency: the gross value leaves the asset account, the depreciation recorded so far
        is cancelled, the sale price leaves the income accounts of the invoices and the rest
        is a gain or a loss.

        :return: (list of (account, balance), book value, sale price)
        """
        self.ensure_one()
        category = self.category_id
        company = self.company_id
        currency = company.currency_id

        def in_company_currency(amount):
            return currency.round(self.currency_id._convert(amount, currency, company, disposal_date))

        gross_value = in_company_currency(self.value)
        accumulated = in_company_currency(
            sum(self.depreciation_line_ids.filtered('move_check').mapped('amount')))
        sale_price_by_account = defaultdict(float)
        for line in sale_lines:
            sale_price_by_account[line.account_id] -= line.balance
        sale_price = currency.round(sum(sale_price_by_account.values()))
        book_value = currency.round(gross_value - accumulated)
        result = currency.round(sale_price - book_value)
        result_account = category.account_asset_gain_id if result > 0 else category.account_asset_loss_id
        if not currency.is_zero(result) and not result_account:
            raise UserError(_('Set the gain and loss accounts of the category "%s".', category.name))

        balances = [(category.account_asset_id, -gross_value),
                    (category.account_depreciation_id, accumulated)]
        balances += [(account, currency.round(amount))
                     for account, amount in sale_price_by_account.items()]
        balances.append((result_account, -result))
        return ([(account, balance) for account, balance in balances
                 if account and not currency.is_zero(balance)], book_value, sale_price)

    def dispose(self, disposal_date=None, sale_lines=None, note=None):
        """ Remove the asset from the books: the depreciation stops on `disposal_date` and a
        draft entry cancels the gross value against the depreciation recorded, booking the
        difference with the sale price as a gain or a loss.

        :param sale_lines: invoice lines recording the sale, none when the asset is scrapped
        :return: action opening the disposal entry
        """
        self.ensure_one()
        sale_lines = sale_lines or self.env['account.move.line']
        disposal_date = disposal_date or fields.Date.context_today(self)
        if not self._in_books():
            raise UserError(_('"%s" is no longer in the books: only an asset that is running '
                              'or fully depreciated can be sold or disposed of.', self.name))
        if disposal_date < self.date:
            raise UserError(_('"%s" cannot be disposed of before its acquisition.', self.name))
        later_moves = self.depreciation_line_ids.filtered('move_check').mapped('move_id').filtered(
            lambda move: move.date > disposal_date)
        if later_moves:
            # they would stay in the books after the asset left them
            raise UserError(_(
                '"%(asset)s" has depreciation entries after %(date)s (%(entries)s): '
                'choose a date on or after the last one.',
                asset=self.name, date=disposal_date,
                entries=', '.join(str(d) for d in sorted(set(later_moves.mapped('date')))),
            ))

        if self.state == 'open':
            self._depreciate_until(disposal_date)
        balances, book_value, sale_price = self._disposal_balances(disposal_date, sale_lines)
        label = _('%s: Sale', self.name) if sale_lines else _('%s: Disposal', self.name)
        move = self.env['account.move'].create({
            'ref': label,
            'date': disposal_date,
            'journal_id': self.category_id.journal_id.id,
            'move_type': 'entry',
            'line_ids': [(0, 0, {
                'name': label,
                'account_id': account.id,
                'balance': balance,
                'analytic_distribution': self.analytic_distribution,
            }) for account, balance in balances],
        })
        result = sale_price - book_value
        self.write({
            'state': 'close',
            'disposal_date': disposal_date,
            'disposal_move_id': move.id,
            'disposal_result': result,
        })
        self.message_post(body=_(
            '%(what)s on %(date)s for %(result)s. %(note)s',
            what=_('Sold') if sale_lines else _('Disposed of'), date=disposal_date,
            result=formatLang(self.env, result, currency_obj=self.company_id.currency_id),
            note=note or ''))
        return self._return_disposal_view([move.id])

    def set_to_close(self):
        """ Dispose of the asset today, without a sale price. """
        for asset in self:
            asset.dispose()
        return self._return_disposal_view(self.disposal_move_id.ids) \
            if self.disposal_move_id else self.open_entries()

    def set_to_draft(self):
        self.write({'state': 'draft'})

    @api.depends('value', 'salvage_value', 'depreciation_line_ids.move_check', 'depreciation_line_ids.amount')
    def _amount_residual(self):
        for rec in self:
            total_amount = 0.0
            for line in rec.depreciation_line_ids:
                if line.move_check:
                    total_amount += line.amount
            rec.value_residual = rec.value - total_amount - rec.salvage_value

    @api.depends('value', 'depreciation_line_ids.move_check', 'depreciation_line_ids.amount')
    def _compute_book_value(self):
        for asset in self:
            recorded = sum(asset.depreciation_line_ids.filtered('move_check').mapped('amount'))
            asset.book_value = asset.value - recorded

    @api.onchange('company_id')
    def onchange_company_id(self):
        self.currency_id = self.company_id.currency_id.id

    @api.onchange('date_first_depreciation')
    def onchange_date_first_depreciation(self):
        for record in self:
            if record.date_first_depreciation == 'manual':
                record.first_depreciation_manual_date = record.date

    @api.depends('depreciation_line_ids.move_id')
    def _entry_count(self):
        for asset in self:
            res = self.env['account.asset.depreciation.line'].search_count([('asset_id', '=', asset.id), ('move_id', '!=', False)])
            asset.entry_count = res or 0

    @api.constrains('prorata', 'method_time')
    def _check_prorata(self):
        # constraints are called with the whole recordset: never touch a field on self
        for asset in self:
            if asset.prorata and asset.method_time != 'number':
                raise ValidationError(_('Prorata temporis can be applied only for the "number of depreciations" time method.'))

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
                    'prorata': category.prorata,
                    'prorata_computation_type': category.prorata_computation_type,
                    'date_first_depreciation': category.date_first_depreciation,
                    'account_analytic_id': category.account_analytic_id.id,
                    'analytic_distribution': category.analytic_distribution,
                }
            }

    @api.onchange('category_id', 'value')
    def _onchange_salvage_value_pct(self):
        for asset in self:
            if asset.category_id.salvage_value_pct:
                asset.salvage_value = asset.category_id._get_salvage_value(asset.value)

    @api.onchange('method_time')
    def onchange_method_time(self):
        if self.method_time != 'number':
            self.prorata = False

    def copy_data(self, default=None):
        if default is None:
            default = {}
        default['name'] = self.name + _(' (copy)')
        return super(AccountAssetAsset, self).copy_data(default)

    def _compute_entries(self, date, group_entries=False):
        depreciation_ids = self.env['account.asset.depreciation.line'].search([
            ('asset_id', 'in', self.ids), ('depreciation_date', '<=', date),
            ('move_check', '=', False)])
        if group_entries:
            return depreciation_ids.create_grouped_move()
        return depreciation_ids.create_move()

    @api.model_create_multi
    def create(self, vals_list):
        assets = super(AccountAssetAsset, self.with_context(mail_create_nolog=True)).create(vals_list)
        for asset in assets:
            asset.sudo().compute_depreciation_board()
        return assets

    def write(self, vals):
        res = super(AccountAssetAsset, self).write(vals)
        if BOARD_FIELDS.intersection(vals) and 'depreciation_line_ids' not in vals:
            # never recompute a closed asset, and never on an unrelated write; a write
            # that already sets the board itself (disposal) must be left alone too
            for rec in self.filtered(lambda asset: asset.state in ('draft', 'open')):
                rec.compute_depreciation_board()
        return res

    def open_entries(self):
        move_ids = []
        for asset in self:
            for depreciation_line in asset.depreciation_line_ids:
                if depreciation_line.move_id:
                    move_ids.append(depreciation_line.move_id.id)
        return {
            'name': _('Journal Entries'),
            'view_type': 'form',
            'view_mode': 'list,form',
            'res_model': 'account.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', move_ids)],
        }


    def _open_assets_action(self, name):
        action = {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.asset.asset',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.ids)],
        }
        if len(self) == 1:
            action.update({'view_mode': 'form', 'res_id': self.id})
        return action

    def open_refunded_asset(self):
        self.ensure_one()
        return self.refunded_asset_id._open_assets_action(self.refunded_asset_id.name)

    def open_refunds(self):
        self.ensure_one()
        return self.refund_ids._open_assets_action(_('Refunds of %s', self.name))

    def activate_depreciation(self, on_date, category, note=None):
        """ Start depreciating an asset kept at its value (no depreciation method), e.g. a building finished or land
        prepared for use, with the method of `category`. When the category books its assets on another account, the
        value is moved there by a journal entry. The life of the asset starts on `on_date`. """
        self.ensure_one()
        if self.method != 'none' or self.state != 'open':
            raise UserError(_('Only running assets without depreciation can have their depreciation activated.'))
        if category.method == 'none':
            raise UserError(_('Choose a category with a depreciation method.'))
        old_account = self.category_id.account_asset_id
        values = self.onchange_category_id_values(category.id)['value']
        values.pop('account_analytic_id', None)
        values.pop('analytic_distribution', None)
        transfer = self.env['account.move']
        if category.account_asset_id != old_account:
            company_currency = self.company_id.currency_id
            balance = self.currency_id._convert(self.value, company_currency, self.company_id, on_date)
            line_vals = {
                'name': _('%s: Depreciation activated', self.name),
                'partner_id': self.partner_id.id,
                'analytic_distribution': self.analytic_distribution,
                'currency_id': self.currency_id.id,
            }
            transfer = self.env['account.move'].create({
                'ref': line_vals['name'],
                'date': on_date,
                'journal_id': category.journal_id.id,
                'move_type': 'entry',
                'partner_id': self.partner_id.id,
                'line_ids': [
                    Command.create({**line_vals, 'account_id': category.account_asset_id.id,
                                    'balance': balance, 'amount_currency': self.value}),
                    Command.create({**line_vals, 'account_id': old_account.id,
                                    'balance': -balance, 'amount_currency': -self.value}),
                ],
            })
            transfer._post(soft=False)
        # the depreciation starts on the day it is activated, in whole periods: the first entry closes the first
        # period; the asset keeps its purchase date
        self.write({
            **values,
            'category_id': category.id,
            'prorata': False,
            'date_first_depreciation': 'manual',
            'first_depreciation_manual_date': on_date + relativedelta(months=category.method_period, days=-1),
        })
        self.compute_depreciation_board()
        body = _('Depreciation activated on %(date)s with the category %(category)s. %(note)s',
                 date=on_date, category=category.name, note=note or '')
        if transfer:
            body = Markup('%s %s') % (body, _('The value is moved to the new account by %s',
                                              transfer._get_html_link()))
        self.message_post(body=body)
        return transfer


class AccountAssetGroup(models.Model):
    """ Assets that belong together, whatever their category: the machines of a production line, the equipment of
    an office, the parts of a building. """
    _name = 'account.asset.group'
    _description = 'Asset Group'
    _order = 'name, id'
    _check_company_auto = True

    name = fields.Char(required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    note = fields.Text()
    asset_ids = fields.One2many('account.asset.asset', 'group_id', string='Assets')
    asset_count = fields.Integer(compute='_compute_asset_count', string='# Assets')

    @api.depends('asset_ids')
    def _compute_asset_count(self):
        counts = dict(self.env['account.asset.asset']._read_group(
            [('group_id', 'in', self.ids)], ['group_id'], ['__count']))
        for group in self:
            group.asset_count = counts.get(group, 0)

    def action_view_assets(self):
        self.ensure_one()
        action = self.asset_ids._open_assets_action(_('Assets of %s', self.name))
        if len(self.asset_ids) != 1:
            action['domain'] = [('group_id', '=', self.id)]
        action['context'] = {'default_group_id': self.id}
        return action


class AccountAssetDepreciationLine(models.Model):
    _name = 'account.asset.depreciation.line'
    _description = 'Asset depreciation line'

    name = fields.Char(string='Depreciation Name', required=True, index=True)
    sequence = fields.Integer(required=True)
    asset_id = fields.Many2one('account.asset.asset', string='Asset',
                               required=True, ondelete='cascade')
    parent_state = fields.Selection(related='asset_id.state',
                                    string='State of Asset')
    amount = fields.Monetary(string='Current Depreciation',
                             required=True)
    remaining_value = fields.Monetary(string='Next Period Depreciation',
                                      required=True)
    depreciated_value = fields.Monetary(string='Cumulative Depreciation',
                                        required=True)
    depreciation_date = fields.Date('Depreciation Date', index=True)
    move_id = fields.Many2one('account.move', string='Depreciation Entry')
    move_check = fields.Boolean(compute='_get_move_check', string='Linked',
                                store=True)
    move_posted_check = fields.Boolean(compute='_get_move_posted_check',
                                       string='Posted', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  related='asset_id.currency_id',
                                  readonly=True)

    @api.depends('move_id')
    def _get_move_check(self):
        for line in self:
            line.move_check = bool(line.move_id)

    @api.depends('move_id.state')
    def _get_move_posted_check(self):
        for line in self:
            line.move_posted_check = True if line.move_id and line.move_id.state == 'posted' else False

    def create_move(self, post_move=True):
        created_moves = self.env['account.move']
        for line in self:
            if line.move_id:
                raise UserError(_('This depreciation is already linked to a journal entry. Please post or delete it.'))
            move_vals = self._prepare_move(line)
            move = self.env['account.move'].create(move_vals)
            line.write({'move_id': move.id, 'move_check': True})
            created_moves |= move

        if post_move and created_moves:
            created_moves.filtered(lambda m: any(m.asset_depreciation_ids.mapped('asset_id.category_id.open_asset'))).action_post()
        return [x.id for x in created_moves]

    def _prepare_move(self, line):
        category_id = line.asset_id.category_id
        analytic_distribution = line.asset_id.analytic_distribution
        depreciation_date = self.env.context.get('depreciation_date') or line.depreciation_date or fields.Date.context_today(self)
        company_currency = line.asset_id.company_id.currency_id
        current_currency = line.asset_id.currency_id
        prec = company_currency.decimal_places
        amount = current_currency._convert(
            line.amount, company_currency, line.asset_id.company_id, depreciation_date)
        asset_name = line.asset_id.name + ' (%s/%s)' % (line.sequence, len(line.asset_id.depreciation_line_ids))
        move_line_1 = {
            'name': asset_name,
            'account_id': category_id.account_depreciation_id.id,
            'debit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
            'credit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
            'partner_id': line.asset_id.partner_id.id,
            'analytic_distribution': analytic_distribution,
            'currency_id': company_currency != current_currency and current_currency.id or company_currency.id,
            'amount_currency': - 1.0 * line.amount
        }
        move_line_2 = {
            'name': asset_name,
            'account_id': category_id.account_depreciation_expense_id.id,
            'credit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
            'debit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
            'partner_id': line.asset_id.partner_id.id,
            'analytic_distribution': analytic_distribution,
            'currency_id': company_currency != current_currency and current_currency.id or company_currency.id,
            'amount_currency': line.amount,
        }
        move_vals = {
            'ref': line.asset_id.code,
            'date': depreciation_date or False,
            'journal_id': category_id.journal_id.id,
            'line_ids': [(0, 0, move_line_1), (0, 0, move_line_2)],
        }
        return move_vals

    def _prepare_move_grouped(self):
        asset_id = self[0].asset_id
        category_id = asset_id.category_id  # we can suppose that all lines have the same category
        account_analytic_id = asset_id.account_analytic_id
        # analytic_tag_ids = asset_id.analytic_tag_ids
        analytic_distribution = asset_id.analytic_distribution

        depreciation_date = self.env.context.get('depreciation_date') or fields.Date.context_today(self)
        amount = 0.0
        for line in self:
            # Sum amount of all depreciation lines
            company_currency = line.asset_id.company_id.currency_id
            current_currency = line.asset_id.currency_id
            company = line.asset_id.company_id
            # convert at the rate of the depreciation date, like _prepare_move does,
            # not at today's rate
            amount += current_currency._convert(
                line.amount, company_currency, company,
                line.depreciation_date or depreciation_date)

        name = category_id.name + _(' (grouped)')
        move_line_1 = {
            'name': name,
            'account_id': category_id.account_depreciation_id.id,
            'debit': 0.0,
            'credit': amount,
            'journal_id': category_id.journal_id.id,
            'analytic_distribution': analytic_distribution,
        }
        move_line_2 = {
            'name': name,
            'account_id': category_id.account_depreciation_expense_id.id,
            'credit': 0.0,
            'debit': amount,
            'journal_id': category_id.journal_id.id,
            'analytic_distribution': analytic_distribution,
        }
        move_vals = {
            'ref': category_id.name,
            'date': depreciation_date or False,
            'journal_id': category_id.journal_id.id,
            'line_ids': [(0, 0, move_line_1), (0, 0, move_line_2)],
        }

        return move_vals

    def create_grouped_move(self, post_move=True):
        if not self.exists():
            return []

        created_moves = self.env['account.move']
        move = self.env['account.move'].create(self._prepare_move_grouped())
        self.write({'move_id': move.id, 'move_check': True})
        created_moves |= move

        if post_move and created_moves:
            created_moves.action_post()
        return [x.id for x in created_moves]

    def post_lines_and_close_asset(self):
        # we re-evaluate the assets to determine whether we can close them
        for line in self:
            line.log_message_when_posted()
            asset = line.asset_id
            # value_residual only counts lines that have a move, draft ones included, so
            # an asset whose board has been fully generated but not posted would be
            # closed here while its entries are still draft
            pending = asset.depreciation_line_ids.filtered(
                lambda l: l.move_id and l.move_id.state != 'posted')
            if not pending and asset.currency_id.is_zero(asset.value_residual):
                asset.message_post(body=_("Document closed."))
                asset.write({'state': 'close'})

    def log_message_when_posted(self):
        def _format_message(message_description, tracked_values):
            message = ''
            if message_description:
                message = '<span>%s</span>' % message_description
            for name, values in tracked_values.items():
                message += '<div> &nbsp; &nbsp; &bull; <b>%s</b>: ' % name
                message += '%s</div>' % values
            return Markup(message)

        for line in self:
            if line.move_id and line.move_id.state == 'draft':
                partner_name = line.asset_id.partner_id.name
                currency_name = line.asset_id.currency_id.name
                msg_values = {_('Currency'): currency_name, _('Amount'): line.amount}
                if partner_name:
                    msg_values[_('Partner')] = partner_name
                msg = _format_message(_('Depreciation line posted.'), msg_values)
                line.asset_id.message_post(body=msg)
    
    def unlink(self):
        for record in self:
            if record.move_check:
                if record.asset_id.category_id.type == 'purchase':
                    msg = _("You cannot delete posted depreciation lines.")
                else:
                    msg = _("You cannot delete posted installment lines.")
                raise UserError(msg)
        return super(AccountAssetDepreciationLine, self).unlink()