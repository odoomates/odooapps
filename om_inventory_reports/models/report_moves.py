from odoo import api, fields, models
from odoo.tools import SQL

# how a done move line counts, seen from the locations of the report
IN_KINDS = ('in_purchase', 'in_production', 'in_return', 'in_adjust', 'in_transfer', 'in_internal')
OUT_KINDS = ('out_sale', 'out_production', 'out_return', 'out_scrap', 'out_adjust', 'out_transfer', 'out_internal')

DIM_COLUMNS = {
    'product': 'product_id',
    'location': 'location_id',
    'lot': 'lot_id',
    'owner': 'owner_id',
}


class OmInventoryReport(models.AbstractModel):
    _inherit = 'om.inventory.report'

    @api.model
    def _om_kind_labels(self):
        return {
            'in_purchase': self.env._("Received from vendors"),
            'in_production': self.env._("Produced"),
            'in_return': self.env._("Customer returns"),
            'in_adjust': self.env._("Adjustments (+)"),
            'in_transfer': self.env._("Transfers in"),
            'in_internal': self.env._("Internal in"),
            'out_sale': self.env._("Delivered to customers"),
            'out_production': self.env._("Consumed in production"),
            'out_return': self.env._("Returned to vendors"),
            'out_scrap': self.env._("Scrapped"),
            'out_adjust': self.env._("Adjustments (-)"),
            'out_transfer': self.env._("Transfers out"),
            'out_internal': self.env._("Internal out"),
        }

    @api.model
    def _om_count_internal(self, options):
        """Moves between two locations of the report count only when the report
        shows locations; otherwise they cancel out and are left out."""
        return bool({'location', 'warehouse'} & set(options['group_by']))

    @api.model
    def _om_move_sides(self, options, location_ids, date_end, extra=None):
        """SQL of the done move lines of the report, one row per side that
        touches the report's locations: + for the line entering one, - for the
        line leaving one. Columns: id, move_id, picking_id, product_id,
        location_id (the report's side), other_location_id, lot_id, owner_id,
        date, qty (signed, in the product's unit), kind."""
        conditions = [
            SQL("sml.state = 'done'"),
            SQL("pt.is_storable"),
            SQL("sml.company_id = ANY(%s)", self.env.companies.ids),
            SQL("sml.date < %s", date_end),
        ]
        product_ids = self._om_product_ids(options)
        if product_ids is not None:
            conditions.append(SQL("sml.product_id = ANY(%s)", product_ids))
        if options.get('lot_ids'):
            conditions.append(SQL("sml.lot_id = ANY(%s)", options['lot_ids']))
        if options.get('owner_ids'):
            conditions.append(SQL("sml.owner_id = ANY(%s)", options['owner_ids']))
        if extra:
            conditions.append(extra)
        where = SQL(" AND ").join(conditions)
        internal = self._om_count_internal(options)
        skip_internal_in = SQL("") if internal else SQL("AND NOT (sml.location_id = ANY(%s))", location_ids)
        skip_internal_out = SQL("") if internal else SQL("AND NOT (sml.location_dest_id = ANY(%s))", location_ids)
        return SQL("""
            SELECT sml.id, sml.move_id, sml.picking_id, sml.product_id,
                   sml.location_dest_id AS location_id, sml.location_id AS other_location_id,
                   sml.lot_id, sml.owner_id, sml.date, sml.quantity_product_uom AS qty,
                   CASE WHEN sml.location_id = ANY(%(locs)s) THEN 'in_internal'
                        WHEN src.usage = 'supplier' THEN 'in_purchase'
                        WHEN src.usage = 'production' THEN 'in_production'
                        WHEN src.usage = 'customer' THEN 'in_return'
                        WHEN src.usage = 'inventory' THEN 'in_adjust'
                        ELSE 'in_transfer' END AS kind
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
              JOIN stock_location src ON src.id = sml.location_id
              JOIN product_product pp ON pp.id = sml.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE %(where)s AND sml.location_dest_id = ANY(%(locs)s) %(skip_in)s
            UNION ALL
            SELECT sml.id, sml.move_id, sml.picking_id, sml.product_id,
                   sml.location_id AS location_id, sml.location_dest_id AS other_location_id,
                   sml.lot_id, sml.owner_id, sml.date, -sml.quantity_product_uom AS qty,
                   CASE WHEN sml.location_dest_id = ANY(%(locs)s) THEN 'out_internal'
                        WHEN sm.is_scrap THEN 'out_scrap'
                        WHEN dest.usage = 'customer' THEN 'out_sale'
                        WHEN dest.usage = 'production' THEN 'out_production'
                        WHEN dest.usage = 'supplier' THEN 'out_return'
                        WHEN dest.usage = 'inventory' THEN 'out_adjust'
                        ELSE 'out_transfer' END AS kind
              FROM stock_move_line sml
              JOIN stock_move sm ON sm.id = sml.move_id
              JOIN stock_location dest ON dest.id = sml.location_dest_id
              JOIN product_product pp ON pp.id = sml.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE %(where)s AND sml.location_id = ANY(%(locs)s) %(skip_out)s
        """, locs=location_ids, where=where, skip_in=skip_internal_in, skip_out=skip_internal_out)

    @api.model
    def _om_move_balances(self, options, date_start=None, date_end=None, dims=None):
        """Quantities by dimension: opening (before ``date_start``), each kind of
        movement between the two dates, and closing (before ``date_end``).

        Rows: {'product_id', 'location_id'?, 'lot_id'?, 'owner_id'?, 'opening',
        <each kind>, 'qty_in', 'qty_out', 'closing'}; out quantities are positive.
        """
        location_ids = self._om_location_ids(options)
        if not location_ids:
            return []
        dims = dims or self._om_row_dimensions(options)
        group_columns = [DIM_COLUMNS[d] for d in DIM_COLUMNS if d in dims]
        date_end = date_end or self._om_datetime_end(fields.Date.to_date(options['date_to']))
        date_start = date_start or date_end
        sides = self._om_move_sides(options, location_ids, date_end)
        kind_sums = [
            SQL("COALESCE(SUM(%s) FILTER (WHERE s.date >= %s AND s.kind = %s), 0) AS %s",
                SQL("s.qty") if kind.startswith('in') else SQL("-s.qty"), date_start, kind, SQL.identifier(kind))
            for kind in IN_KINDS + OUT_KINDS
        ]
        query = SQL("""
            SELECT %(group)s,
                   COALESCE(SUM(s.qty) FILTER (WHERE s.date < %(start)s), 0) AS opening,
                   %(kinds)s,
                   COALESCE(SUM(s.qty), 0) AS closing
              FROM (%(sides)s) s
          GROUP BY %(group)s
        """, group=SQL(", ").join(SQL.identifier('s', c) for c in group_columns),
            start=date_start, kinds=SQL(", ").join(kind_sums), sides=sides)
        self.env.cr.execute(query)
        rows = self.env.cr.dictfetchall()
        for row in rows:
            row['qty_in'] = sum(row[k] for k in IN_KINDS)
            row['qty_out'] = sum(row[k] for k in OUT_KINDS)
        return rows

    @api.model
    def _om_move_details(self, options, node, date_start, date_end):
        """The move lines of a leaf between two dates, oldest first, as dicts."""
        node_options, location_ids = self._om_node_scope(options, node)
        if not location_ids:
            return []
        sides = self._om_move_sides(node_options, location_ids, date_end)
        query = SQL("""
            SELECT s.*, sm.reference, sm.origin, sm.picking_type_id, sm.is_inventory, sm.is_scrap,
                   COALESCE(sm.partner_id, sp.partner_id) AS partner_id
              FROM (%s) s
              JOIN stock_move sm ON sm.id = s.move_id
         LEFT JOIN stock_picking sp ON sp.id = s.picking_id
             WHERE s.date >= %s
          ORDER BY s.date, s.id, s.qty DESC
        """, sides, date_start)
        self.env.cr.execute(query)
        return self.env.cr.dictfetchall()

    @api.model
    def _om_node_scope(self, options, node):
        """(options, location ids) of the report restricted to a node."""
        node_filters = self._om_node_filters(node)
        node_options = dict(options)
        for key in ('product_ids', 'category_ids', 'lot_ids', 'owner_ids'):
            if key in node_filters:
                node_options[key] = node_filters[key]
        location_ids = self._om_location_ids(options)
        if 'warehouse_ids' in node_filters:
            in_warehouse = set(self._om_location_ids({**options, 'warehouse_ids': node_filters['warehouse_ids']}))
            location_ids = [loc for loc in location_ids if loc in in_warehouse]
        if 'location_ids' in node_filters:
            location_ids = [loc for loc in location_ids if loc in node_filters['location_ids']]
        return node_options, location_ids

    @api.model
    def _om_move_open(self, move):
        if move.get('picking_id'):
            return {'res_model': 'stock.picking', 'res_id': move['picking_id']}
        return {'res_model': 'stock.move', 'res_id': move['move_id']}

    @api.model
    def _om_period_bounds(self, options):
        """(start, end) naive UTC datetimes of the report period."""
        end = self._om_datetime_end(fields.Date.to_date(options['date_to']))
        if options.get('date_from'):
            return self._om_datetime_start(fields.Date.to_date(options['date_from'])), end
        return end, end
