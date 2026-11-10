import calendar

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _last_day(day):
    return day.day == calendar.monthrange(day.year, day.month)[1]


def _days_360(start, end):
    """ The days from ``start`` to the end of the day ``end``, every month counting 30 days: the
    calendar By Months spreads an amount with. """
    first = 30 if _last_day(start) else start.day
    after = end + relativedelta(days=1)
    last = min(after.day, 30)
    return 360 * (after.year - start.year) + 30 * (after.month - start.month) + last - first


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    om_deferred_start_date = fields.Date(
        string='Start Date',
        help="First day of the period this line belongs to. Set it together "
             "with an end date to spread the amount over those periods.")
    om_deferred_end_date = fields.Date(
        string='End Date',
        help="Last day of the period this line belongs to.")

    @api.constrains('om_deferred_start_date', 'om_deferred_end_date')
    def _check_om_deferred_dates(self):
        for line in self:
            start, end = line.om_deferred_start_date, line.om_deferred_end_date
            if start and end and start > end:
                raise ValidationError(_(
                    "The deferral of %(label)s starts on %(start)s, after it "
                    "ends on %(end)s.",
                    label=line.name or line.product_id.display_name or '',
                    start=start, end=end,
                ))
            if bool(start) != bool(end):
                raise ValidationError(_(
                    "A deferral needs both a start and an end date."))

    # ------------------------------------------------------------------
    # The schedule
    # ------------------------------------------------------------------
    def _om_deferral_kind(self):
        """ 'expense' for a cost, 'revenue' for income. """
        self.ensure_one()
        return 'expense' if self.account_id.internal_group == 'expense' else 'revenue'

    def _om_deferred_settings(self):
        self.ensure_one()
        return self.company_id._om_deferred_settings(self._om_deferral_kind())

    def _om_is_deferrable(self):
        """ Whether the line asks to be deferred: a line of what was bought or sold, on a profit and
        loss account, with both dates. Which deferral account is used follows from its side of profit
        and loss, so nothing has to be chosen by hand. """
        self.ensure_one()
        return bool(
            self.om_deferred_start_date
            and self.om_deferred_end_date
            and self.display_type in ('product', 'cogs')
            and self.account_id.internal_group in ('income', 'expense')
            and not self.company_id.currency_id.is_zero(self.balance)
        )

    def _om_month_periods(self):
        """ The calendar months the deferral spans, clipped to its own dates: 15 Jan to 20 Mar is
        15-31 Jan, the whole of February and 1-20 Mar. """
        self.ensure_one()
        start, end = self.om_deferred_start_date, self.om_deferred_end_date
        periods = []
        cursor = start
        while cursor <= end:
            month_end = cursor + relativedelta(day=31)
            periods.append((cursor, min(month_end, end)))
            cursor = month_end + relativedelta(days=1)
        return periods

    def _om_month_weights(self, method, periods):
        """ What each month of ``periods`` is worth, in units consistent between the months of the line:
        the amounts are their shares of the sum. """
        start, end = self.om_deferred_start_date, self.om_deferred_end_date
        if method == 'day':
            return [(period_end - period_start).days + 1 for period_start, period_end in periods]
        if method == 'full_month':
            # only the whole months between the dates count, the first ones of the deferral
            months = 12 * (end.year - start.year) + end.month - start.month + (1 if _last_day(end) else 0)
            months = max(months, 1)
            return [1 if index < months else 0 for index in range(len(periods))]
        return [_days_360(period_start, period_end) for period_start, period_end in periods]

    def _om_period_end(self, day, periodicity):
        """ The end of the period ``day`` belongs to: its month, or its fiscal year. """
        if periodicity == 'year':
            return self.company_id.compute_fiscalyear_dates(day)['date_to']
        return day + relativedelta(day=31)

    def _om_deferral_periods(self):
        """ The periods of the deferral with their weights: [(start, end, weight)], monthly or one per
        fiscal year, clipped to the dates of the line. """
        self.ensure_one()
        settings = self._om_deferred_settings()
        months = self._om_month_periods()
        weights = self._om_month_weights(settings['method'], months)
        periods = []
        for (start, end), weight in zip(months, weights):
            period_end = min(self._om_period_end(start, settings['periodicity']), self.om_deferred_end_date)
            if periods and periods[-1][1] == period_end:
                periods[-1] = (periods[-1][0], period_end, periods[-1][2] + weight)
            else:
                periods.append((start, period_end, weight))
        return periods

    def _om_deferral_schedule(self):
        """ When to recognise what: [(date, balance)], at the end of each period. The amounts add back
        up to the balance of the line exactly: every period but the last is rounded to the currency,
        and the last one takes what is left. A period worth nothing gets no amount. """
        self.ensure_one()
        periods = self._om_deferral_periods()
        if not periods:
            return []
        total_weight = sum(weight for _start, _end, weight in periods)
        currency = self.company_id.currency_id
        total = self.balance
        schedule = []
        recognised = 0.0
        for index, (_start, end, weight) in enumerate(periods):
            if index == len(periods) - 1 or not total_weight:
                amount = currency.round(total - recognised)
            else:
                amount = currency.round(total * weight / total_weight)
            recognised += amount
            if not currency.is_zero(amount):
                schedule.append((end, amount))
        return schedule

    def _om_needs_deferral(self):
        """ Whether the line recognises anything outside the period of its document: deferred over
        several periods, or over a single one that is not the period of the document. """
        self.ensure_one()
        if not self._om_is_deferrable():
            return False
        periods = self._om_deferral_periods()
        if len(periods) > 1:
            return True
        periodicity = self._om_deferred_settings()['periodicity']
        return bool(periods) and self._om_period_end(self.move_id.date, periodicity) != \
            self._om_period_end(periods[0][0], periodicity)

    # ------------------------------------------------------------------
    # Reports and the grouped entries
    # ------------------------------------------------------------------
    @api.model
    def _om_deferred_lines(self, kind, grouped_only=True):
        """ The posted lines of the current company deferred outside the period of their document,
        of costs (``kind`` expense) or income (revenue). ``grouped_only`` leaves out the documents
        deferred on their own validation, which Manually & Grouped must not defer a second time. """
        domain = [
            ('company_id', '=', self.env.company.id),
            ('parent_state', '=', 'posted'),
            ('om_deferred_start_date', '!=', False),
            ('om_deferred_end_date', '!=', False),
            ('display_type', 'in', ('product', 'cogs')),
            ('account_id.internal_group', '=', 'expense' if kind == 'expense' else 'income'),
        ]
        if grouped_only:
            domain.append(('move_id.om_deferral_ids', '=', False))
        lines = self.search(domain, order='om_deferred_start_date, id')
        return lines.filtered(lambda line: line._om_needs_deferral())

    def _om_deferral_split(self, date_from, date_to):
        """ The amounts of the line as the deferred reports show them for a period: not started,
        recognised before it, in it, and after it. """
        self.ensure_one()
        values = {'total': self.balance, 'not_started': 0.0, 'before': 0.0, 'current': 0.0, 'later': 0.0}
        if self.om_deferred_start_date > date_to:
            values['not_started'] = self.balance
            return values
        for date, amount in self._om_deferral_schedule():
            if date < date_from:
                values['before'] += amount
            elif date > date_to:
                values['later'] += amount
            else:
                values['current'] += amount
        return values
