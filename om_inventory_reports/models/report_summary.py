from odoo import api, models
from odoo.tools.translate import LazyTranslate

from .report_moves import IN_KINDS, OUT_KINDS

_lt = LazyTranslate(__name__)


class OmInventoryReportSummary(models.AbstractModel):
    """Opening, what came in and went out by kind of movement, closing."""
    _name = 'om.inventory.report.summary'
    _inherit = 'om.inventory.report'
    _description = 'Inventory Summary Report'

    _report_key = 'summary'
    _report_name = _lt('Inventory Summary')
    _report_section = 'movement'
    _report_sequence = 30
    _report_icon = 'table_chart'
    _report_description = _lt('Opening, receipts and issues by kind, closing, for a period.')
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot', 'owner')
    _report_group_by = ('category', 'product', 'warehouse', 'location', 'lot', 'owner')
    _report_default_group_by = ('category', 'product')
    _report_bar_column = 'closing'
    _report_compare_keys = ('qty_in', 'qty_out', 'closing')

    @api.model
    def _om_get_columns(self, options):
        labels = self._om_kind_labels()
        internal = self._om_count_internal(options)
        columns = [{'key': 'opening', 'label': self.env._("Opening"), 'type': 'float', 'aggregate': 'sum'}]
        for kind in IN_KINDS:
            if kind == 'in_internal' and not internal:
                continue
            columns.append({'key': kind, 'label': labels[kind], 'type': 'float', 'aggregate': 'sum',
                            'visible': False, 'group': 'in'})
        columns.append({'key': 'qty_in', 'label': self.env._("Total In"), 'type': 'float', 'aggregate': 'sum'})
        for kind in OUT_KINDS:
            if kind == 'out_internal' and not internal:
                continue
            columns.append({'key': kind, 'label': labels[kind], 'type': 'float', 'aggregate': 'sum',
                            'visible': False, 'group': 'out'})
        columns += [
            {'key': 'qty_out', 'label': self.env._("Total Out"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'closing', 'label': self.env._("Closing"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]
        # the main kinds are shown by default
        for column in columns:
            if column['key'] in ('in_purchase', 'in_production', 'out_sale', 'out_production', 'out_scrap'):
                column['visible'] = True
        return columns

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        return self._om_move_balances(options, start, end)

    @api.model
    def _om_get_kpis(self, data, options):
        total = data['total']['values']
        rows = data['rows']
        return [
            {'key': 'opening', 'label': self.env._("Opening"), 'value': total.get('opening', 0), 'type': 'float',
             'icon': 'history'},
            {'key': 'qty_in', 'label': self.env._("Total in"), 'value': total.get('qty_in', 0), 'type': 'float',
             'icon': 'south_east', 'tone': 'success'},
            {'key': 'qty_out', 'label': self.env._("Total out"), 'value': total.get('qty_out', 0),
             'type': 'float', 'icon': 'north_east', 'tone': 'danger'},
            {'key': 'closing', 'label': self.env._("Closing"), 'value': total.get('closing', 0), 'type': 'float',
             'icon': 'inventory_2'},
            {'key': 'no_move', 'label': self.env._("Products not moved"),
             'value': len([r for r in rows if not r['qty_in'] and not r['qty_out']]), 'type': 'int',
             'icon': 'hourglass_empty', 'tone': 'warning', 'filter': 'no_move'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'no_move':
            return [r for r in rows if not r['qty_in'] and not r['qty_out']]
        return rows
