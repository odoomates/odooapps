from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate

from .report_slow_moving import USE_KINDS

_lt = LazyTranslate(__name__)


class OmInventoryReportTurnover(models.AbstractModel):
    """How fast the stock turns: what was used in the period against the
    average stock, and how many days the closing stock covers."""
    _name = 'om.inventory.report.turnover'
    _inherit = 'om.inventory.report'
    _description = 'Stock Turnover Report'

    _report_key = 'turnover'
    _report_name = _lt('Stock Turnover')
    _report_section = 'analysis'
    _report_sequence = 65
    _report_icon = 'autorenew'
    _report_description = _lt('Turnover ratio and days of cover, by product or category.')
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('category', 'product', 'warehouse', 'location')
    _report_default_group_by = ('category', 'product')
    _report_date_mode = 'range'
    _report_bar_column = 'issued'
    _report_compare_keys = ('issued', 'closing', 'turnover')

    @api.model
    def _om_default_options(self):
        options = super()._om_default_options()
        options['date_preset'] = 'this_year'
        return options

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'opening', 'label': self.env._("Opening"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'closing', 'label': self.env._("Closing"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'average', 'label': self.env._("Average Stock"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("(Opening + Closing) / 2")},
            {'key': 'issued', 'label': self.env._("Used"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("Delivered to customers and consumed in production during the period.")},
            {'key': 'turnover', 'label': self.env._("Turnover"), 'type': 'ratio', 'optional': False,
             'help': self.env._("Used / Average Stock: how many times the stock turned in the period.")},
            {'key': 'cover', 'label': self.env._("Days of Cover"), 'type': 'days',
             'help': self.env._("How many days the closing stock lasts at the period's pace.")},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        rows = self._om_move_balances(options, start, end)
        for row in rows:
            row['issued'] = sum(row[k] for k in USE_KINDS)
            row['average'] = (max(row['opening'], 0.0) + max(row['closing'], 0.0)) / 2
        return rows

    @api.model
    def _om_days(self, options):
        days = (fields.Date.to_date(options['date_to']) - fields.Date.to_date(options['date_from'])).days + 1
        return max(days, 1)

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        values = node['values']
        values['turnover'] = values['issued'] / values['average'] if values['average'] > 0 else 0.0
        daily = values['issued'] / self._om_days(options)
        values['cover'] = values['closing'] / daily if daily > 0 else False
        if options.get('compare'):
            average, issued = values.get('average_cmp') or 0.0, values.get('issued_cmp') or 0.0
            values['turnover_cmp'] = issued / average if average > 0 else 0.0
        if values['average'] > 0 and not values['issued']:
            values['turnover_tone'] = 'danger'
        elif values['turnover'] and values['turnover'] < 1:
            values['turnover_tone'] = 'warning'

    @api.model
    def _om_get_kpis(self, data, options):
        total = data['total']['values']
        rows = data['rows']
        idle = [r for r in rows if r['average'] > 0 and not r['issued']]
        return [
            {'key': 'turnover', 'label': self.env._("Turnover"), 'value': total.get('turnover', 0), 'type': 'ratio',
             'icon': 'autorenew'},
            {'key': 'cover', 'label': self.env._("Days of cover"), 'value': total.get('cover') or 0, 'type': 'days',
             'icon': 'calendar_today'},
            {'key': 'issued', 'label': self.env._("Units used"), 'value': total.get('issued', 0), 'type': 'float',
             'icon': 'north_east'},
            {'key': 'average', 'label': self.env._("Average stock"), 'value': total.get('average', 0),
             'type': 'float', 'icon': 'inventory_2'},
            {'key': 'idle', 'label': self.env._("Stocked, not used"), 'value': len({r['product_id'] for r in idle}),
             'type': 'int', 'icon': 'hourglass_empty', 'tone': 'warning' if idle else 'success', 'filter': 'idle'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'idle':
            return [r for r in rows if r['average'] > 0 and not r['issued']]
        return rows
