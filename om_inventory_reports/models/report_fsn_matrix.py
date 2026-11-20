from odoo import api, models
from odoo.tools.translate import LazyTranslate

from .report_slow_moving import USE_KINDS
from .report_turnover import FSN_TONES, fsn_class

_lt = LazyTranslate(__name__)

VALUE_CLASSES = ('A', 'B', 'C')
FSN_CLASSES = ('F', 'S', 'N')


class OmInventoryReportFsnMatrix(models.AbstractModel):
    """Each product placed by how fast it moves (FSN, from its turnover) and by
    how much of the stock value it holds (A, B, C), with what to do about it:
    a non-moving product holding a large share of the value is the first to
    sell off, a fast one with little value can be ordered in bulk."""
    _name = 'om.inventory.report.fsn_matrix'
    _inherit = 'om.inventory.report'
    _description = 'FSN x Value Matrix Report'

    _report_key = 'fsn_matrix'
    _report_name = _lt('FSN × Value Matrix')
    _report_section = 'analysis'
    _report_sequence = 67
    _report_icon = 'view_module'
    _report_description = _lt('Products by movement (fast, slow, non-moving) and by share of stock value, '
                              'with what to do.')
    _report_filters = ('warehouse', 'location', 'product', 'category')
    _report_group_by = ('segment', 'value_class', 'fsn_class', 'category', 'product')
    _report_default_group_by = ('segment', 'product')
    _report_extra_options = {'fast_ratio': 3, 'slow_ratio': 1, 'a_pct': 70, 'b_pct': 90}
    _report_bar_column = 'value'

    @api.model
    def _om_default_options(self):
        options = super()._om_default_options()
        options['date_preset'] = 'this_year'
        return options

    @api.model
    def _om_fsn_labels(self):
        return self.env['om.inventory.report.turnover']._om_fsn_labels()

    @api.model
    def _om_actions(self):
        """What to do with the products of each segment, most urgent first."""
        return {
            'A-N': self.env._("Sell off or return: high value tied up"),
            'B-N': self.env._("Clear out"),
            'A-S': self.env._("Cut stock levels"),
            'C-N': self.env._("Clear out or write off"),
            'B-S': self.env._("Order less, less often"),
            'A-F': self.env._("Keep in stock, watch closely"),
            'C-S': self.env._("Order on demand"),
            'B-F': self.env._("Keep in stock"),
            'C-F': self.env._("Keep in stock, order in bulk"),
        }

    @api.model
    def _om_dimensions(self):
        dimensions = super()._om_dimensions()
        fsn_labels = self._om_fsn_labels()
        dimensions['segment'] = {
            'label': self.env._("Segment"),
            'icon': 'view_module',
            'selection': {
                key: '%s %s · %s' % (key[0], fsn_labels[key[2]], action)
                for key, action in self._om_actions().items()
            },
        }
        dimensions['value_class'] = {
            'label': self.env._("Value Class"),
            'icon': 'payments',
            'selection': {c: self.env._("Class %s", c) for c in VALUE_CLASSES},
        }
        dimensions['fsn_class'] = {
            'label': self.env._("FSN Class"),
            'icon': 'speed',
            'selection': fsn_labels,
        }
        return dimensions

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'closing', 'label': self.env._("On Hand"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'value', 'label': self.env._("Stock Value"), 'type': 'monetary', 'aggregate': 'sum',
             'optional': False},
            {'key': 'share', 'label': self.env._("Share of Value"), 'type': 'percent', 'aggregate': 'sum'},
            {'key': 'issued', 'label': self.env._("Used in Period"), 'type': 'float', 'aggregate': 'sum',
             'help': self.env._("Delivered to customers and consumed in production during the period.")},
            {'key': 'average', 'label': self.env._("Average Stock"), 'type': 'float', 'aggregate': 'sum',
             'visible': False, 'help': self.env._("(Opening + Closing) / 2")},
            {'key': 'turnover', 'label': self.env._("Turnover"), 'type': 'ratio',
             'help': self.env._("Used / average stock of the period.")},
            {'key': 'fsn', 'label': self.env._("FSN"), 'type': 'char'},
            {'key': 'value_class', 'label': self.env._("Value Class"), 'type': 'char',
             'help': self.env._("A holds the first share of the stock value (70 % by default), B the next "
                                "(up to 90 %), C the rest.")},
            {'key': 'action', 'label': self.env._("What to Do"), 'type': 'char'},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_row_dimensions(self, options):
        return {'product'}

    @api.model
    def _om_count_internal(self, options):
        return False

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        fast = float(options.get('fast_ratio') or 3)
        slow = min(float(options.get('slow_ratio') or 1), fast)
        rows = []
        for row in self._om_move_balances(options, start, end):
            row['issued'] = sum(row[k] for k in USE_KINDS)
            if row['closing'] <= 0 and row['issued'] <= 0:
                continue
            row['average'] = (max(row['opening'], 0.0) + max(row['closing'], 0.0)) / 2
            row['fsn_class_id'] = fsn_class(row['issued'], row['average'], fast, slow)
            rows.append(row)
        costs = self._om_product_costs([r['product_id'] for r in rows], options)
        for row in rows:
            row['value'] = max(row['closing'], 0.0) * costs.get(row['product_id'], 0.0)
        total = sum(r['value'] for r in rows)
        a_pct = float(options.get('a_pct') or 70)
        b_pct = max(float(options.get('b_pct') or 90), a_pct)
        cumulative = 0.0
        for row in sorted(rows, key=lambda r: -r['value']):
            row['share'] = row['value'] / total * 100 if total else 0.0
            # a product is in the class where its share starts; no value is C
            if row['value'] <= 0:
                row['value_class_id'] = 'C'
            else:
                row['value_class_id'] = 'A' if cumulative < a_pct else 'B' if cumulative < b_pct else 'C'
            cumulative += row['share']
            row['segment_id'] = '%s-%s' % (row['value_class_id'], row['fsn_class_id'])
        return rows

    @api.model
    def _om_filter_rows(self, rows, options, columns):
        if options['kpi_filter']:
            rows = self._om_kpi_filter_rows(rows, options['kpi_filter'], options)
        return rows

    @api.model
    def _om_finalize_node(self, node, options):
        super()._om_finalize_node(node, options)
        values = node['values']
        values['turnover'] = values['issued'] / values['average'] if values.get('average') else False
        rows = node['rows']
        segments = {r['segment_id'] for r in rows}
        if len(segments) == 1:
            segment = segments.pop()
            values['value_class'] = self.env._("Class %s", segment[0])
            values['fsn'] = self._om_fsn_labels()[segment[2]]
            values['fsn_tone'] = FSN_TONES[segment[2]]
            values['action'] = self._om_actions()[segment]
            if segment in ('A-N', 'B-N'):
                values['action_tone'] = 'danger'
            elif segment in ('A-S', 'C-N'):
                values['action_tone'] = 'warning'

    @api.model
    def _om_extra_options_meta(self, options):
        return [
            {'key': 'fast_ratio', 'label': self.env._("Fast above turnover of"), 'min': 0, 'step': 0.5},
            {'key': 'slow_ratio', 'label': self.env._("Slow from turnover of"), 'min': 0, 'step': 0.5},
            {'key': 'a_pct', 'label': self.env._("Class A up to (% of value)"), 'min': 1, 'step': 1},
            {'key': 'b_pct', 'label': self.env._("Class B up to (% of value)"), 'min': 1, 'step': 1},
        ]

    @api.model
    def _om_toggles(self):
        return [t for t in super()._om_toggles() if t['key'] != 'hide_zero']

    @api.model
    def _om_get_kpis(self, data, options):
        rows = data['all_rows']
        non_moving = [r for r in rows if r['fsn_class_id'] == 'N']
        sell_off = [r for r in rows if r['segment_id'] == 'A-N']
        return [
            {'key': 'value', 'label': self.env._("Stock value"), 'value': sum(r['value'] for r in rows),
             'type': 'monetary', 'icon': 'payments'},
            {'key': 'non_moving', 'label': self.env._("Value in non-moving products"),
             'value': sum(r['value'] for r in non_moving), 'type': 'monetary', 'icon': 'block',
             'tone': 'danger' if non_moving else 'success', 'filter': 'N'},
            {'key': 'sell_off', 'label': self.env._("High value, not moving"), 'value': len(sell_off),
             'type': 'int', 'icon': 'warning', 'tone': 'danger' if sell_off else 'success', 'filter': 'A-N'},
            {'key': 'products', 'label': self.env._("Products"), 'value': len(rows), 'type': 'int',
             'icon': 'inventory_2'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi in FSN_CLASSES:
            return [r for r in rows if r['fsn_class_id'] == kpi]
        if kpi in self._om_actions():
            return [r for r in rows if r['segment_id'] == kpi]
        return rows

    @api.model
    def _om_get_chart(self, data, options):
        """The 3 x 3 grid: value classes down, FSN classes across; each cell
        with its products and their value, and a click narrows to it."""
        rows = data['all_rows']
        if not rows:
            return None
        fsn_labels = self._om_fsn_labels()
        actions = self._om_actions()
        cells = {}
        for value_class in VALUE_CLASSES:
            cells[value_class] = {}
            for fsn in FSN_CLASSES:
                segment = '%s-%s' % (value_class, fsn)
                members = [r for r in rows if r['segment_id'] == segment]
                cells[value_class][fsn] = {
                    'value': len(members),
                    'amount': sum(r['value'] for r in members),
                    'caption': actions[segment],
                    'tone': 'danger' if segment in ('A-N', 'B-N') else 'warning'
                    if segment in ('A-S', 'C-N') else 'success' if fsn == 'F' else 'neutral',
                    'filter': segment,
                }
        return {
            'type': 'matrix',
            'title': self.env._("Movement against stock value"),
            'value_type': 'int',
            'amount_type': 'monetary',
            'rows': [{'key': c, 'label': self.env._("Class %s", c)} for c in VALUE_CLASSES],
            'cols': [{'key': f, 'label': fsn_labels[f]} for f in FSN_CLASSES],
            'cells': cells,
        }
