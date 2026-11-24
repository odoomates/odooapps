from . import models
from . import wizard


def post_init_hook(env):
    env['stock.warehouse'].search([])._om_rental_create_location()
    # Confirmed rental orders may have got deliveries when Inventory was installed before this module:
    # rental lines move their stock at pickup and return instead.
    lines = env['sale.order.line'].search([('is_rental', '=', True), ('state', '=', 'sale')])
    if not lines:
        return
    moves = lines.move_ids.filtered(lambda move: move.state not in ('done', 'cancel'))
    pickings = moves.picking_id
    moves._action_cancel()
    pickings.filtered(lambda picking: not (picking.move_ids - moves)).unlink()
    lines._compute_qty_delivered_method()
    for line in lines.filtered(lambda line: line.qty_delivered_method == 'manual'):
        line.qty_delivered = line.qty_picked_up
