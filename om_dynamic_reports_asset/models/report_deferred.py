from collections import defaultdict
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools.misc import format_date

from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

# periods in a schedule at most before months become quarters, then quarters years
MAX_MONTHS = 24
MAX_QUARTERS = 24
# the accounts of a prepaid expense: what is paid in advance, not a fixed asset
PREPAID_ACCOUNT_TYPES = ('asset_prepayments', 'asset_current')


class OmDynamicReportDeferred(models.AbstractModel):
    """Recognition schedule of deferrals: per deferral (an asset of Assets
    Management), what it recognizes before the period, in each month (quarter,
    year) of the period, and later; by category.

    The amounts are those of the depreciation boards of the assets: the lines
    with a posted entry, and the planned ones too unless only the posted
    recognitions are asked for.
    """
    _name = 'om.dynamic.report.deferred'
    _inherit = 'om.dynamic.report'
    _description = 'Dynamic Deferral Schedule'

    _report_section = 'ledgers'
    _report_group = 'account.group_account_readonly,account.group_account_manager'

    @api.model
    def _om_name_label(self, options):
        return self.env._("Deferral")

    @api.model
    def _odr_category_domain(self):
        return []

    @api.model
    def _om_filters(self):
        return [
            {'key': 'category_ids', 'label': self.env._("Categories"), 'model': 'account.asset.category',
             'icon': 'category', 'domain': self._odr_category_domain()},
            *self._odr_filters('partner_ids'),
        ]

    @api.model
    def _om_choices(self):
        return [{'key': 'recognition', 'label': self.env._("Recognitions"), 'icon': 'event_repeat', 'menu': 'bar',
                 'default': 'all', 'choices': [['all', self.env._("Posted and planned")],
                                               ['posted', self.env._("Posted only")]]}]

    # ------------------------------------------------------------------
    # Periods and columns
    # ------------------------------------------------------------------

    @api.model
    def _odr_buckets(self, options):
        """[(key, label, start, end)] of the periods of the schedule: months, or quarters, or years."""
        start, end = fields.Date.to_date(options['date_from']), fields.Date.to_date(options['date_to'])
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        step = 1 if months <= MAX_MONTHS else 3 if months <= MAX_QUARTERS * 3 else 12
        buckets = []
        cursor = start
        while cursor <= end:
            stop = min(cursor + relativedelta(months=step, days=-1), end)
            if step == 1:
                label = format_date(self.env, cursor, date_format='MMM yyyy')
            elif step == 3:
                label = 'Q%s %s' % ((cursor.month - 1) // 3 + 1, cursor.year)
            else:
                label = str(cursor.year)
            buckets.append(('p_%s' % cursor.strftime('%Y%m%d'), label, cursor, stop))
            cursor = stop + relativedelta(days=1)
        return buckets

    @api.model
    def _om_get_columns(self, options):
        columns = [
            {'key': 'start', 'label': self.env._("Start"), 'type': 'date'},
            {'key': 'total', 'label': self.env._("Total"), 'type': 'monetary', 'optional': False},
            {'key': 'before', 'label': self.env._("Before"), 'type': 'monetary', 'drill': True,
             'help': self.env._("Recognized before the period.")},
        ]
        for key, label, _start, _stop in self._odr_buckets(options):
            columns.append({'key': key, 'label': label, 'type': 'monetary', 'drill': True,
                            'group': self._om_period_label(options)})
        columns.append({'key': 'later', 'label': self.env._("Later"), 'type': 'monetary', 'drill': True,
                        'help': self.env._("Still to recognize after the period.")})
        return columns

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @api.model
    def _odr_assets(self, options):
        domain = [('company_id', 'in', self._odr_company_ids()), ('state', 'in', ('open', 'close')),
                  ('category_id', 'in', self.env['account.asset.category'].search(self._odr_category_domain()).ids)]
        if options['category_ids']:
            domain.append(('category_id', 'in', options['category_ids']))
        if options['partner_ids']:
            domain.append(('partner_id', 'in', options['partner_ids']))
        return self.env['account.asset.asset'].search(domain, order='date, id')

    @api.model
    def _odr_board_domain(self, asset_ids, options):
        domain = [('asset_id', 'in', asset_ids)]
        if options['recognition'] == 'posted':
            domain.append(('move_posted_check', '=', True))
        return domain

    @api.model
    def _odr_board_lines(self, assets, options):
        """The lines of the depreciation boards of ``assets`` the report counts."""
        return self.env['account.asset.depreciation.line'].search(
            self._odr_board_domain(assets.ids, options), order='depreciation_date, id')

    @api.model
    def _odr_entries_action(self, name, lines, extra_moves=None):
        """The journal entries of board lines (a planned line has none yet)."""
        moves = lines.move_id | (extra_moves or self.env['account.move'])
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'account.move',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', moves.ids)],
            'context': {'create': False},
            'target': 'current',
        }

    @api.model
    def _odr_bucket_of(self, day, options, buckets):
        if day < fields.Date.to_date(options['date_from']):
            return 'before'
        if day > fields.Date.to_date(options['date_to']):
            return 'later'
        return next(key for key, _label, start, stop in buckets if start <= day <= stop)

    @api.model
    def _odr_asset_amount(self, amount, asset):
        """An amount of an asset, in its currency, in the currency of the report."""
        currency = self._om_currency()
        if asset.currency_id == currency:
            return amount
        date = self.env.context.get('odr_rate_date') or fields.Date.context_today(self)
        return asset.currency_id._convert(amount, currency, self.env.company, date, round=False)

    @api.model
    def _odr_tree(self, options):
        buckets = self._odr_buckets(options)
        keys = ['total', 'before'] + [key for key, *_rest in buckets] + ['later']
        assets = self._odr_assets(options)
        values = {asset.id: dict.fromkeys(keys, 0.0) for asset in assets}
        for line in self._odr_board_lines(assets, options):
            amount = self._odr_asset_amount(line.amount, line.asset_id)
            row = values[line.asset_id.id]
            row[self._odr_bucket_of(line.depreciation_date, options, buckets)] += amount
            row['total'] += amount
        currency = self._om_currency()
        by_category = defaultdict(list)
        for asset in assets:
            if not currency.is_zero(values[asset.id]['total']):
                by_category[asset.category_id].append(asset)
        nodes = []
        total = dict.fromkeys(keys, 0.0)
        for category in sorted(by_category, key=lambda c: (c.name or '').casefold()):
            category_id = 'category-%s' % category.id
            children = []
            category_values = dict.fromkeys(keys, 0.0)
            for asset in by_category[category]:
                row = values[asset.id]
                for key in keys:
                    category_values[key] += row[key]
                asset_id = '%s|asset-%s' % (category_id, asset.id)
                name = '%s (%s)' % (asset.name, asset.partner_id.display_name) if asset.partner_id else asset.name
                children.append(self._odr_node(asset_id, name, self._om_line(
                    asset_id, name, {**row, 'start': fields.Date.to_string(asset.date)}, parent_id=category_id,
                    level=1, kind='leaf', open_record=('account.asset.asset', asset.id), drill=True,
                    drill_label=self.env._("Recognition entries"))))
            for key in keys:
                total[key] += category_values[key]
            nodes.append(self._odr_node(category_id, category.name, self._om_line(
                category_id, category.name, category_values, kind='group', has_children=True,
                count=len(children), unfolded=True), children))
        return nodes, total if nodes else False

    # ------------------------------------------------------------------
    # Drill-down
    # ------------------------------------------------------------------

    @api.model
    def _odr_recognition_action(self, options, line_id, column_key=None):
        asset_id = self._odr_line_id_part(line_id, 'asset')
        if not asset_id:
            return False
        asset = self.env['account.asset.asset'].browse(asset_id)
        domain = self._odr_board_domain([asset_id], options)
        if column_key == 'before':
            domain.append(('depreciation_date', '<', options['date_from']))
        elif column_key == 'later':
            domain.append(('depreciation_date', '>', options['date_to']))
        elif column_key:
            bucket = next((b for b in self._odr_buckets(options) if b[0] == column_key), None)
            if not bucket:
                return False
            domain += [('depreciation_date', '>=', bucket[2]), ('depreciation_date', '<=', bucket[3])]
        lines = self.env['account.asset.depreciation.line'].search(domain)
        return self._odr_entries_action(self.env._("Recognitions of %s", asset.name), lines)

    @api.model
    def _om_line_action(self, options, line_id):
        return self._odr_recognition_action(options, line_id)

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        return self._odr_recognition_action(options, line_id, column_key)


class OmDynamicReportDeferredRevenue(models.AbstractModel):
    _name = 'om.dynamic.report.deferred.revenue'
    _inherit = 'om.dynamic.report.deferred'
    _description = 'Dynamic Deferred Revenue'

    _report_name = 'Deferred Revenue'
    _report_description = _lt("Revenue invoiced in advance, recognized month by month.")
    _report_sequence = 50
    _report_icon = 'event_upcoming'

    @api.model
    def _om_report_title(self):
        return self.env._("Deferred Revenue")

    @api.model
    def _odr_category_domain(self):
        return [('type', '=', 'sale')]


class OmDynamicReportDeferredExpense(models.AbstractModel):
    """Prepaid expenses: the purchase deferrals of Assets Management kept on a
    prepayment or current asset account, not the fixed assets."""
    _name = 'om.dynamic.report.deferred.expense'
    _inherit = 'om.dynamic.report.deferred'
    _description = 'Dynamic Deferred Expense'

    _report_name = 'Deferred Expense'
    _report_description = _lt("Expenses paid in advance, recognized month by month.")
    _report_sequence = 51
    _report_icon = 'event_available'

    @api.model
    def _om_report_title(self):
        return self.env._("Deferred Expense")

    @api.model
    def _odr_category_domain(self):
        return [('type', '=', 'purchase'), ('account_asset_id.account_type', 'in', PREPAID_ACCOUNT_TYPES)]


class OmDynamicReportDepreciation(models.AbstractModel):
    """Depreciation Schedule: per fixed asset, by category, its gross value and
    its accumulated depreciation at the start of the period, what the period
    added and removed, and both at its end with the net book value.

    The figures are those of the boards of Assets Management: the
    depreciation lines, a sale or disposal removing what was left.
    """
    _name = 'om.dynamic.report.depreciation'
    _inherit = 'om.dynamic.report.deferred'
    _description = 'Dynamic Depreciation Schedule'

    _report_name = 'Depreciation Schedule'
    _report_description = _lt("Gross value, depreciation and net book value of every fixed asset.")
    _report_sequence = 52
    _report_icon = 'precision_manufacturing'

    @api.model
    def _om_report_title(self):
        return self.env._("Depreciation Schedule")

    @api.model
    def _om_name_label(self, options):
        return self.env._("Asset")

    @api.model
    def _odr_category_domain(self):
        # the fixed assets: the prepaid expenses are in the Deferred Expense
        return [('type', '=', 'purchase'), ('account_asset_id.account_type', 'not in', PREPAID_ACCOUNT_TYPES)]

    @api.model
    def _om_choices(self):
        return [{'key': 'recognition', 'label': self.env._("Depreciations"), 'icon': 'event_repeat',
                 'menu': 'bar', 'default': 'posted', 'choices': [['posted', self.env._("Posted only")],
                                                                 ['all', self.env._("Posted and planned")]]}]

    @api.model
    def _om_get_columns(self, options):
        gross, depreciation = self.env._("Gross Value"), self.env._("Depreciation")
        return [
            {'key': 'start', 'label': self.env._("Acquired"), 'type': 'date'},
            {'key': 'gross_opening', 'label': self.env._("Opening"), 'type': 'monetary', 'group': gross},
            {'key': 'gross_additions', 'label': self.env._("Additions"), 'type': 'monetary', 'group': gross},
            {'key': 'gross_disposals', 'label': self.env._("Disposals"), 'type': 'monetary', 'group': gross},
            {'key': 'gross_closing', 'label': self.env._("Closing"), 'type': 'monetary', 'group': gross},
            {'key': 'dep_opening', 'label': self.env._("Opening"), 'type': 'monetary', 'group': depreciation,
             'drill': True},
            {'key': 'dep_period', 'label': self.env._("Period"), 'type': 'monetary', 'group': depreciation,
             'drill': True},
            {'key': 'dep_disposals', 'label': self.env._("Disposals"), 'type': 'monetary', 'group': depreciation,
             'drill': True},
            {'key': 'dep_closing', 'label': self.env._("Closing"), 'type': 'monetary', 'group': depreciation,
             'drill': True},
            {'key': 'book_value', 'label': self.env._("Net Book Value"), 'type': 'monetary', 'optional': False},
        ]

    @api.model
    def _odr_asset_figures(self, asset, lines, date_from, date_to):
        """The columns of an asset over the period, in the currency of the asset."""
        gross = asset.value
        acquired = asset.date
        disposed = asset.disposal_date if asset.state == 'close' and asset.disposal_date else False

        def accumulated(day):
            """Depreciation accumulated at the end of ``day``, before a full disposal on it."""
            if acquired > day:
                return 0.0
            return sum(lines.filtered(lambda line: line.depreciation_date <= day).mapped('amount'))

        def gross_at(day):
            return 0.0 if acquired > day else gross

        day_before = date_from - timedelta(days=1)
        gone_before = disposed and disposed < date_from
        values = {
            'gross_opening': 0.0 if gone_before else gross_at(day_before),
            'gross_additions': gross if date_from <= acquired <= date_to else 0.0,
            'dep_opening': 0.0 if gone_before else accumulated(day_before),
            'dep_period': sum(lines.filtered(
                lambda line: date_from <= line.depreciation_date <= date_to).mapped('amount')),
            'gross_disposals': 0.0,
            'dep_disposals': 0.0,
        }
        if disposed and date_from <= disposed <= date_to:
            values['gross_disposals'] += gross_at(disposed)
            values['dep_disposals'] += accumulated(disposed)
        values['gross_closing'] = values['gross_opening'] + values['gross_additions'] - values['gross_disposals']
        values['dep_closing'] = values['dep_opening'] + values['dep_period'] - values['dep_disposals']
        values['book_value'] = values['gross_closing'] - values['dep_closing']
        return values

    @api.model
    def _odr_tree(self, options):
        date_from, date_to = fields.Date.to_date(options['date_from']), fields.Date.to_date(options['date_to'])
        assets = self._odr_assets(options).filtered(lambda a: a.date <= date_to)
        lines = self._odr_board_lines(assets, options)
        lines_by_asset = {asset.id: lines.filtered(lambda line, a=asset: line.asset_id == a)
                          for asset in assets}
        keys = [key for key in ('gross_opening', 'gross_additions', 'gross_disposals', 'gross_closing',
                                'dep_opening', 'dep_period', 'dep_disposals', 'dep_closing', 'book_value')]
        currency = self._om_currency()
        by_category = defaultdict(list)
        for asset in assets:
            values = self._odr_asset_figures(asset, lines_by_asset[asset.id], date_from, date_to)
            values = {key: self._odr_asset_amount(value, asset) for key, value in values.items()}
            if not all(currency.is_zero(values[key]) for key in keys):
                by_category[asset.category_id].append((asset, values))
        nodes = []
        total = dict.fromkeys(keys, 0.0)
        for category in sorted(by_category, key=lambda c: (c.name or '').casefold()):
            category_id = 'category-%s' % category.id
            category_values = dict.fromkeys(keys, 0.0)
            children = []
            for asset, values in by_category[category]:
                for key in keys:
                    category_values[key] += values[key]
                asset_id = '%s|asset-%s' % (category_id, asset.id)
                children.append(self._odr_node(asset_id, asset.name, self._om_line(
                    asset_id, asset.name, {**values, 'start': fields.Date.to_string(asset.date)},
                    parent_id=category_id, level=1, kind='leaf', open_record=('account.asset.asset', asset.id),
                    drill=True, drill_label=self.env._("Depreciation entries"))))
            for key in keys:
                total[key] += category_values[key]
            nodes.append(self._odr_node(category_id, category.name, self._om_line(
                category_id, category.name, category_values, kind='group', has_children=True,
                count=len(children), unfolded=True), children))
        return nodes, total if nodes else False

    @api.model
    def _om_cell_action(self, options, line_id, column_key):
        """The depreciation entries of a figure: before the period, in it, up to its end."""
        asset_id = self._odr_line_id_part(line_id, 'asset')
        if not asset_id:
            return False
        asset = self.env['account.asset.asset'].browse(asset_id)
        Line = self.env['account.asset.depreciation.line']
        name = self.env._("Depreciations of %s", asset.name)
        domain = self._odr_board_domain([asset_id], options)
        if column_key == 'dep_opening':
            domain.append(('depreciation_date', '<', options['date_from']))
        elif column_key == 'dep_period':
            domain += [('depreciation_date', '>=', options['date_from']),
                       ('depreciation_date', '<=', options['date_to'])]
        elif column_key == 'dep_disposals':
            # the entry that removed the asset from the books
            disposed = asset.disposal_move_id.filtered(
                lambda move: options['date_from'] <= fields.Date.to_string(move.date) <= options['date_to'])
            return self._odr_entries_action(name, Line, disposed)
        else:
            domain.append(('depreciation_date', '<=', options['date_to']))
        return self._odr_entries_action(name, Line.search(domain))

    @api.model
    def _om_line_action(self, options, line_id):
        return self._om_cell_action(options, line_id, 'dep_closing')
