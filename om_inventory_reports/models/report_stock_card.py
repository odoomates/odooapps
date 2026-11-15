from odoo import api, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)


class OmInventoryReportStockCard(models.AbstractModel):
    """The ledger of a product: opening balance, every receipt and issue of
    the period with its running balance, and the closing balance."""
    _name = 'om.inventory.report.stock_card'
    _inherit = 'om.inventory.report'
    _description = 'Stock Card Report'

    _report_key = 'stock_card'
    _report_name = _lt('Stock Card')
    _report_section = 'movement'
    _report_sequence = 20
    _report_icon = 'receipt_long'
    _report_description = _lt('Product ledger: opening, each receipt and issue, running balance, closing.')
    _report_filters = ('warehouse', 'location', 'product', 'category', 'lot', 'owner')
    _report_group_by = ('category', 'product', 'warehouse', 'location', 'lot', 'owner')
    _report_default_group_by = ('product',)
    _report_has_details = True

    @api.model
    def _om_get_columns(self, options):
        return [
            {'key': 'date', 'label': self.env._("Date"), 'type': 'datetime', 'detail_only': True, 'sortable': False},
            {'key': 'reference', 'label': self.env._("Reference"), 'type': 'char', 'detail_only': True},
            {'key': 'partner', 'label': self.env._("Partner"), 'type': 'char', 'detail_only': True},
            {'key': 'movement', 'label': self.env._("Movement"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'location', 'label': self.env._("From / To"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'lot', 'label': self.env._("Lot/Serial"), 'type': 'char', 'detail_only': True,
             'visible': False},
            {'key': 'opening', 'label': self.env._("Opening"), 'type': 'float', 'aggregate': 'sum'},
            {'key': 'qty_in', 'label': self.env._("In"), 'type': 'float', 'aggregate': 'sum', 'optional': False},
            {'key': 'qty_out', 'label': self.env._("Out"), 'type': 'float', 'aggregate': 'sum', 'optional': False},
            {'key': 'balance', 'label': self.env._("Balance"), 'type': 'float', 'aggregate': 'sum',
             'optional': False},
            {'key': 'uom', 'label': self.env._("Unit"), 'type': 'char'},
        ]

    @api.model
    def _om_get_rows(self, options):
        start, end = self._om_period_bounds(options)
        rows = self._om_move_balances(options, start, end)
        for row in rows:
            row['balance'] = row['closing']
        return rows

    @api.model
    def _om_detail_lines(self, node, options):
        start, end = self._om_period_bounds(options)
        moves = self._om_move_details(options, node, start, end)
        opening = node['values'].get('opening', 0.0)
        lines = [self._om_detail_line(node, 'open', self.env._("Opening balance"), {
            'balance': opening, 'uom': node['values'].get('uom')}, kind='opening')]
        partners = self._om_names('partner', list({m['partner_id'] for m in moves if m['partner_id']}))
        location_ids = list({m['other_location_id'] for m in moves} | {m['location_id'] for m in moves})
        locations = self._om_names('location', location_ids)
        lots = self._om_names('lot', list({m['lot_id'] for m in moves if m['lot_id']}))
        kinds = self._om_kind_labels()
        balance = opening
        for move in moves:
            balance += move['qty']
            if move['qty'] >= 0:
                route = '%s → %s' % (locations.get(move['other_location_id'], ''), locations.get(move['location_id'], ''))
            else:
                route = '%s → %s' % (locations.get(move['location_id'], ''), locations.get(move['other_location_id'], ''))
            lines.append(self._om_detail_line(node, move['id'] * (1 if move['qty'] >= 0 else -1),
                                              move['reference'] or move['origin'] or '', {
                'date': move['date'],
                'reference': move['origin'] if move['origin'] and move['origin'] != move['reference'] else '',
                'partner': partners.get(move['partner_id'], ''),
                'movement': kinds.get(move['kind'], ''),
                'location': route,
                'lot': lots.get(move['lot_id'], ''),
                'qty_in': move['qty'] if move['qty'] > 0 else 0.0,
                'qty_out': -move['qty'] if move['qty'] < 0 else 0.0,
                'balance': balance,
                'uom': node['values'].get('uom'),
                'move_id': move['move_id'],
                'qty': move['qty'],
            }, open_action=self._om_move_open(move)))
        lines.append(self._om_detail_line(node, 'close', self.env._("Closing balance"), {
            'qty_in': node['values'].get('qty_in'), 'qty_out': node['values'].get('qty_out'),
            'balance': node['values'].get('balance'), 'uom': node['values'].get('uom')}, kind='closing'))
        return lines

    @api.model
    def _om_get_kpis(self, data, options):
        total = data['total']['values']
        return [
            {'key': 'opening', 'label': self.env._("Opening"), 'value': total.get('opening', 0), 'type': 'float',
             'icon': 'history'},
            {'key': 'qty_in', 'label': self.env._("Received"), 'value': total.get('qty_in', 0), 'type': 'float',
             'icon': 'south_east', 'tone': 'success', 'filter': 'in'},
            {'key': 'qty_out', 'label': self.env._("Issued"), 'value': total.get('qty_out', 0), 'type': 'float',
             'icon': 'north_east', 'tone': 'danger', 'filter': 'out'},
            {'key': 'balance', 'label': self.env._("Closing"), 'value': total.get('balance', 0), 'type': 'float',
             'icon': 'inventory_2'},
            {'key': 'moved', 'label': self.env._("Products moved"),
             'value': len({r['product_id'] for r in data['rows'] if r['qty_in'] or r['qty_out']}), 'type': 'int',
             'icon': 'sync_alt', 'filter': 'moved'},
        ]

    @api.model
    def _om_kpi_filter_rows(self, rows, kpi, options):
        if kpi == 'in':
            return [r for r in rows if r['qty_in']]
        if kpi == 'out':
            return [r for r in rows if r['qty_out']]
        if kpi == 'moved':
            return [r for r in rows if r['qty_in'] or r['qty_out']]
        return rows
