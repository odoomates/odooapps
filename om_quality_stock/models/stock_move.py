from odoo import fields, models
from odoo.fields import Domain


class StockMove(models.Model):
    _inherit = 'stock.move'

    om_quality_evaluated = fields.Boolean(copy=False, help="The control points of the move were looked at.")
    om_quality_check_id = fields.Many2one('om.quality.check', string='Quality Check', index='btree_not_null', copy=False,
                                          help="The failed check this scrap comes from.")

    def _action_confirm(self, merge=True, merge_into=False, create_proc=True):
        moves = super()._action_confirm(merge=merge, merge_into=merge_into, create_proc=create_proc)
        moves._om_quality_create_checks()
        return moves

    def _om_quality_create_checks(self):
        """ The checks of the control points on transfers that match the moves. Once per lot
        points of tracked products wait for the lots, at validation. """
        moves = self.filtered(lambda m: m.picking_id and not m.om_quality_evaluated and not m.is_scrap
                              and m.state not in ('draft', 'cancel', 'done'))
        if not moves:
            return self.env['om.quality.check']
        moves.sudo().om_quality_evaluated = True
        created = self.env['om.quality.check']
        for company, company_moves in moves.grouped('company_id').items():
            points = self.env['om.quality.point']._get_points('picking', company)
            if not points:
                continue
            for move in company_moves:
                picking = move.picking_id
                candidates = points.filtered(lambda p: move.picking_type_id in p.picking_type_ids)
                for point in candidates._filter_product(move.product_id, picking.partner_id):
                    if point.frequency == 'lot' and move.product_id.tracking != 'none':
                        continue
                    if not point._should_check(move.product_id):
                        continue
                    created |= picking._om_quality_create_checks(point, move.product_id, picking.partner_id, {
                        'picking_id': picking.id,
                        'move_id': move.id,
                        'quantity': move.product_qty,
                    })
        return created

    def _action_cancel(self):
        res = super()._action_cancel()
        checks = self.env['om.quality.check'].sudo().search([
            ('move_id', 'in', self.filtered(lambda m: m.state == 'cancel').ids), ('state', '=', 'todo')])
        checks.write({'state': 'cancel'})
        return res

    def _action_scrap(self):
        res = super()._action_scrap()
        self.filtered('om_quality_check_id').om_quality_check_id._om_quality_after_scrap()
        return res

    # ------------------------------------------------------------
    # Lots on hold and quarantine kept out of reservation
    # ------------------------------------------------------------

    def _om_quality_skip_held(self, lot_id, strict):
        return (not strict and not lot_id and self.product_id.tracking != 'none'
                and self.company_id.om_quality_lot_hold_reservation
                and not self.env.context.get('om_quality_allow_held'))

    def _update_reserved_quantity(self, need, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        if self._om_quality_skip_held(lot_id, strict):
            return super(StockMove, self.with_context(om_quality_skip_held=True))._update_reserved_quantity(
                need, location_id, lot_id, package_id, owner_id, strict)
        return super()._update_reserved_quantity(need, location_id, lot_id, package_id, owner_id, strict)

    def _get_available_quantity(self, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, allow_negative=False):
        if self._om_quality_skip_held(lot_id, strict):
            return super(StockMove, self.with_context(om_quality_skip_held=True))._get_available_quantity(
                location_id, lot_id, package_id, owner_id, strict, allow_negative)
        return super()._get_available_quantity(location_id, lot_id, package_id, owner_id, strict, allow_negative)

    def _get_available_move_lines(self, assigned_moves_ids, partially_available_moves_ids):
        """ The next step of a route does not take goods out of a quarantine location. """
        available = super()._get_available_move_lines(assigned_moves_ids, partially_available_moves_ids)
        return {key: quantity for key, quantity in available.items() if not key[0].om_quality_quarantine}


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_gather_domain(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False):
        domain = super()._get_gather_domain(product_id, location_id, lot_id, package_id, owner_id, strict)
        if self.env.context.get('om_quality_skip_held'):
            domain &= Domain('lot_id', '=', False) | Domain('lot_id.om_quality_state', '=', 'ok')
        return domain
