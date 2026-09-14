from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

SCHEDULE_COLUMNS = (
    'asset_opening', 'asset_increase', 'asset_decrease', 'asset_closing',
    'depreciation_opening', 'depreciation_increase', 'depreciation_decrease', 'depreciation_closing',
    'book_value',
)


class AssetDepreciationSchedule(models.TransientModel):
    _name = 'asset.depreciation.schedule'
    _description = 'Depreciation Schedule'

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Start Date', required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string='End Date', required=True, default=lambda self: self._default_date_to())
    category_ids = fields.Many2many(
        'account.asset.category', string='Asset Categories',
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        help="Leave empty to include every asset category.",
    )
    group_by_category = fields.Boolean(string='Group by Category', default=True)

    def _default_date_from(self):
        return self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_from']

    def _default_date_to(self):
        return self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_to']

    def _get_assets(self):
        domain = [
            ('company_id', '=', self.company_id.id),
            ('category_id.type', '=', 'purchase'),
            ('state', 'in', ('open', 'paused', 'close')),
            ('date', '<=', self.date_to),
            '|', ('disposal_date', '=', False), ('disposal_date', '>=', self.date_from),
        ]
        if self.category_ids:
            domain.append(('category_id', 'in', self.category_ids.ids))
        return self.env['account.asset.asset'].with_context(active_test=False).search(domain, order='category_id, date, id')

    def _get_asset_values(self, asset):
        """ Movements of the gross value and of the accumulated depreciation of `asset`
        between `date_from` and `date_to`, in company currency, from posted entries. """
        company = self.company_id
        currency = company.currency_id

        def convert(amount, date):
            return asset.currency_id._convert(amount, currency, company, date)

        acquired_before = asset.date < self.date_from
        gross_value = convert(asset.value, asset.date)
        imported = convert(asset.opening_depreciation, asset.date)
        vals = dict.fromkeys(SCHEDULE_COLUMNS, 0.0)
        vals['asset_opening' if acquired_before else 'asset_increase'] = gross_value
        vals['depreciation_opening' if acquired_before else 'depreciation_increase'] = imported
        for move in asset._get_board_moves().filtered(lambda m: m.state == 'posted' and m.date <= self.date_to):
            amount = convert(move.asset_depreciation_amount, move.date)
            vals['depreciation_opening' if move.date < self.date_from else 'depreciation_increase'] += amount
        if asset.disposal_date and asset.disposal_date <= self.date_to:
            vals['asset_decrease'] = vals['asset_opening'] + vals['asset_increase']
            vals['depreciation_decrease'] = vals['depreciation_opening'] + vals['depreciation_increase']
        vals['asset_closing'] = vals['asset_opening'] + vals['asset_increase'] - vals['asset_decrease']
        vals['depreciation_closing'] = vals['depreciation_opening'] + vals['depreciation_increase'] - vals['depreciation_decrease']
        vals['book_value'] = vals['asset_closing'] - vals['depreciation_closing']
        return {key: currency.round(value) for key, value in vals.items()}

    def _get_method_label(self, asset):
        method = dict(asset._fields['method']._description_selection(self.env))[asset.method]
        if asset.method_time == 'rate':
            duration = _('%s %% / year', asset.method_rate)
        elif asset.method_time == 'end':
            duration = _('until %s', format_date(self.env, asset.method_end))
        else:
            duration = _('%(number)s × %(period)s months', number=asset.method_number, period=asset.method_period)
        return '%s, %s' % (method, duration)

    def _get_schedule_data(self):
        """ :return: list of groups ``{'name', 'lines': [{'asset', 'method', **values}], 'totals'}``
        and the grand total. """
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('The start date must be before the end date.'))
        groups = {}
        for asset in self._get_assets():
            key = asset.category_id if self.group_by_category else False
            group = groups.setdefault(key, {
                'name': asset.category_id.name if self.group_by_category else _('All Assets'),
                'lines': [],
                'totals': dict.fromkeys(SCHEDULE_COLUMNS, 0.0),
            })
            values = self._get_asset_values(asset)
            group['lines'].append({'asset': asset, 'method': self._get_method_label(asset), **values})
            for column in SCHEDULE_COLUMNS:
                group['totals'][column] += values[column]
        currency = self.company_id.currency_id
        total = dict.fromkeys(SCHEDULE_COLUMNS, 0.0)
        for group in groups.values():
            for column in SCHEDULE_COLUMNS:
                group['totals'][column] = currency.round(group['totals'][column])
                total[column] += group['totals'][column]
        return list(groups.values()), {column: currency.round(value) for column, value in total.items()}

    def action_print(self):
        self.ensure_one()
        return self.env.ref('om_account_asset.action_report_depreciation_schedule').report_action(self)


class ReportDepreciationSchedule(models.AbstractModel):
    _name = 'report.om_account_asset.report_depreciation_schedule'
    _description = 'Depreciation Schedule Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['asset.depreciation.schedule'].browse(docids)
        groups, total = wizard._get_schedule_data()
        return {
            'doc_ids': docids,
            'doc_model': 'asset.depreciation.schedule',
            'docs': wizard,
            'groups': groups,
            'total': total,
            'currency': wizard.company_id.currency_id,
            'columns': SCHEDULE_COLUMNS,
        }
