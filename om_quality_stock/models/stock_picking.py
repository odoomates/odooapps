from odoo import fields, models
from odoo.fields import Domain


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'om.quality.document.mixin']

    om_quality_check_ids = fields.One2many('om.quality.check', 'picking_id', string='Quality Check Records')

    def _om_quality_check_domain(self):
        return Domain('picking_id', 'in', self.ids)

    def _om_quality_document_of_check(self, check):
        return check.picking_id

    def _om_quality_create_lot_checks(self):
        """ Control points once per lot: a check for each lot of the transfer not checked yet. """
        Check = self.env['om.quality.check']
        created = Check
        for picking in self.filtered(lambda p: p.state not in ('done', 'cancel')):
            points = self.env['om.quality.point']._get_points(
                'picking', picking.company_id,
                [('frequency', '=', 'lot'), ('picking_type_ids', 'in', picking.picking_type_id.ids)])
            if not points:
                continue
            per_lot = {}
            for line in picking.move_line_ids:
                if line.product_id.tracking == 'none' or not (line.lot_id or line.lot_name):
                    continue
                key = (line.product_id, line.lot_id, line.lot_id.name or line.lot_name)
                entry = per_lot.setdefault(key, {'quantity': 0.0, 'move': line.move_id})
                entry['quantity'] += line.quantity_product_uom
            for (product, lot, lot_name), entry in per_lot.items():
                for point in points._filter_product(product, picking.partner_id):
                    domain = Check._om_quality_lot_domain(product, lot=lot or None, lot_name=lot_name) & \
                        Domain('point_id', '=', point.id) & Domain('state', '!=', 'cancel')
                    if Check.sudo().search_count(domain, limit=1):
                        continue
                    created |= picking._om_quality_create_checks(point, product, picking.partner_id, {
                        'picking_id': picking.id,
                        'move_id': entry['move'].id,
                        'lot_id': lot.id,
                        'lot_name': lot_name,
                        'quantity': entry['quantity'],
                    })
        return created

    def _pre_action_done_hook(self):
        self._om_quality_create_lot_checks()
        blocking = self._om_quality_blocking_checks()
        if blocking:
            return blocking.picking_id._om_quality_block_action(blocking)
        return super()._pre_action_done_hook()

    def _action_done(self):
        res = super()._action_done()
        checks = self.om_quality_check_ids.filtered(lambda c: c.state != 'cancel')
        checks._om_quality_link_lots()
        checks.filtered(lambda c: c.state == 'failed' or c.disposition)._om_quality_apply_lot_state()
        return res

    def action_om_quality_dialog(self):
        self._om_quality_create_lot_checks()
        return super().action_om_quality_dialog()

    def action_om_quality_certificate(self):
        return self.env.ref('om_quality_stock.action_report_om_quality_certificate').report_action(self)

    def _om_quality_certificate_lines(self):
        """ What the certificate shows, per product and lot delivered: the passed checks of the
        delivery, and the passed checks of the delivered lots on other documents. """
        self.ensure_one()
        Check = self.env['om.quality.check'].sudo()
        groups = []
        moves = self.move_ids.filtered(lambda m: m.state != 'cancel')
        for move in moves:
            lots = move.move_line_ids.lot_id
            for lot in lots or [self.env['stock.lot']]:
                domain = Domain('state', '=', 'passed') & Domain('product_id', '=', move.product_id.id)
                if lot:
                    domain &= Domain('picking_id', '=', self.id) | Domain('lot_id', '=', lot.id)
                else:
                    domain &= Domain('picking_id', '=', self.id)
                checks = Check.search(domain, order='date_done, id')
                quantity = sum(move.move_line_ids.filtered(lambda line: line.lot_id == lot).mapped('quantity')) if lot else move.quantity
                groups.append({
                    'product': move.product_id,
                    'lot': lot,
                    'quantity': quantity,
                    'uom': move.uom_id,
                    'checks': checks,
                })
        return groups
