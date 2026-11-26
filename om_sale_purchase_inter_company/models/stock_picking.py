from collections import defaultdict

from odoo import models
from odoo.fields import Domain
from odoo.tools import float_is_zero


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super()._action_done()
        if not self.env.context.get('om_ic_no_mirror'):
            self._om_ic_validate_receipts()
        return res

    def _om_ic_validate_receipts(self):
        """Validate the receipts of the purchase orders of the other companies linked with the sales orders
        these deliveries are for, with the quantities, lots and serial numbers delivered."""
        for picking in self.sudo().filtered(lambda p: p.state == 'done' and p.picking_type_code == 'outgoing'):
            sale = picking.sale_id
            purchase = sale.om_ic_purchase_id
            if not purchase or purchase.state != 'purchase':
                continue
            rule = sale.om_ic_rule_id or purchase.om_ic_rule_id
            if not rule or not rule.sync_receipt:
                continue
            picking._om_ic_validate_receipt(rule, sale, purchase)

    def _om_ic_receipt_plan(self, purchase):
        """{receipt move: [(quantity, lot name)]} of the receipts of ``purchase`` matching this delivery."""
        self.ensure_one()
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        receipt_moves = purchase.picking_ids.filtered(
            lambda p: p.picking_type_code == 'incoming' and p.state not in ('done', 'cancel')).move_ids.filtered(
            lambda m: m.state not in ('done', 'cancel'))
        plan = defaultdict(list)
        left = {move: move.product_uom_qty for move in receipt_moves}
        for move in self.move_ids.filtered(lambda m: m.state == 'done' and m.sale_line_id):
            purchase_line = move.sale_line_id.om_ic_purchase_line_id
            targets = receipt_moves.filtered(lambda m, pl=purchase_line: m.purchase_line_id == pl)
            if not targets:
                continue
            for move_line in move.move_line_ids.filtered('quantity'):
                quantity = move_line.uom_id._compute_quantity(move_line.quantity, targets[0].uom_id)
                lot = move_line.lot_id.name or move_line.lot_name or False
                for target in targets:
                    if float_is_zero(quantity, precision_digits=precision):
                        break
                    take = quantity if target == targets[-1] else min(quantity, max(left[target], 0.0))
                    if float_is_zero(take, precision_digits=precision):
                        continue
                    plan[target].append((take, lot))
                    left[target] -= take
                    quantity -= take
        return plan

    def _om_ic_validate_receipt(self, rule, sale, purchase):
        self.ensure_one()
        plan = self._om_ic_receipt_plan(purchase)
        if not plan:
            return
        company = purchase.company_id

        def validate(env):
            Lot = env['stock.lot']
            receipts = env['stock.picking']
            for move, quantities in plan.items():
                move = env['stock.move'].browse(move.id)
                move.move_line_ids.unlink()
                tracked = move.product_id.tracking != 'none'
                for quantity, lot_name in quantities:
                    line_vals = {
                        'move_id': move.id,
                        'picking_id': move.picking_id.id,
                        'product_id': move.product_id.id,
                        'uom_id': move.uom_id.id,
                        'quantity': quantity,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'company_id': company.id,
                        'picked': True,
                    }
                    if tracked and lot_name:
                        lot = Lot.search(Domain('name', '=', lot_name) & Domain('product_id', '=', move.product_id.id)
                                         & Domain('company_id', 'in', [company.id, False]), limit=1)
                        if not lot:
                            lot = Lot.create({'name': lot_name, 'product_id': move.product_id.id,
                                              'company_id': company.id})
                        line_vals['lot_id'] = lot.id
                    env['stock.move.line'].create(line_vals)
                move.picked = True
                receipts |= move.picking_id
            receipts.with_context(cancel_backorder=False)._action_done()
            for receipt in receipts:
                receipt.message_post(body=self.env._(
                    "Validated with %(delivery)s of %(company)s.", delivery=self._get_html_link(),
                    company=self.company_id.name))
            self.message_post(body=self.env._(
                "%(receipts)s of %(company)s validated with this delivery.",
                receipts=', '.join(receipts.mapped('name')), company=company.name))

        done, error = sale._om_ic_run(rule, company, validate)
        if not done:
            warning = self.env._("The receipt of %(order)s in %(company)s was not validated: %(error)s",
                                 order=purchase.name, company=company.name, error=error)
            sale._om_ic_warn(warning)
            purchase._om_ic_warn(warning)
