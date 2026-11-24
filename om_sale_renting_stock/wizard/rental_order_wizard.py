from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class OmRentalOrderWizard(models.TransientModel):
    _inherit = 'om.rental.order.wizard'

    def _om_rental_process_stock(self):
        res = super()._om_rental_process_stock()
        for line in self.line_ids.filtered(lambda l: l.uom_id.compare(l.qty, 0) > 0):
            line._om_rental_move_stock()
        return res


class OmRentalOrderWizardLine(models.TransientModel):
    _inherit = 'om.rental.order.wizard.line'

    tracking = fields.Selection(related='product_id.tracking')
    is_storable = fields.Boolean(related='product_id.is_storable')
    available_lot_ids = fields.Many2many(
        'stock.lot', 'om_rental_wizard_line_available_lot_rel', 'line_id', 'lot_id',
        compute='_compute_available_lot_ids')
    lot_ids = fields.Many2many(
        'stock.lot', 'om_rental_wizard_line_lot_rel', 'line_id', 'lot_id', string="Serial Numbers", compute='_compute_lot_ids', store=True, readonly=False,
        domain="[('id', 'in', available_lot_ids)]")

    @api.depends('sale_line_id', 'wizard_id.mode')
    def _compute_available_lot_ids(self):
        for line in self:
            sol = line.sale_line_id
            if not sol or line.tracking in (False, 'none'):
                line.available_lot_ids = False
            elif line.wizard_id.mode == 'return':
                line.available_lot_ids = sol._om_rental_out_lots()
            else:
                line.available_lot_ids = sol._om_rental_available_lots()

    @api.depends('sale_line_id', 'wizard_id.mode', 'available_lot_ids')
    def _compute_lot_ids(self):
        for line in self:
            if line.tracking in (False, 'none') or not line.sale_line_id:
                line.lot_ids = False
                continue
            sol = line.sale_line_id
            if line.wizard_id.mode == 'return':
                line.lot_ids = sol._om_rental_out_lots()
                continue
            count = int(line.qty_max) if line.tracking == 'serial' else 1
            reserved = (sol.rental_lot_ids & line.available_lot_ids) - sol.rental_pickedup_lot_ids
            proposed = reserved | (line.available_lot_ids - reserved - sol.rental_pickedup_lot_ids)
            line.lot_ids = proposed[:count]

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        if self.tracking == 'serial' and self.lot_ids:
            self.qty = len(self.lot_ids)

    def _om_rental_move_stock(self):
        self.ensure_one()
        sol = self.sale_line_id
        product = self.product_id
        if not product.is_storable:
            return
        warehouse = sol._rental_get_warehouse()
        if not warehouse:
            return
        warehouse._om_rental_create_location()
        mode = self.wizard_id.mode
        qty = self.uom_id._compute_quantity(self.qty, product.uom_id)
        if mode == 'pickup':
            source, dest = warehouse.lot_stock_id, warehouse.rental_location_id
        else:
            source, dest = warehouse.rental_location_id, warehouse.lot_stock_id
            # only what was moved out (lines picked up without stock moves are skipped)
            qty = min(qty, sol._om_rental_moved_out_qty())
            if product.uom_id.compare(qty, 0) <= 0:
                return
        lots = self.lot_ids
        if product.tracking == 'serial':
            if product.uom_id.compare(len(lots), qty) != 0:
                raise UserError(self.env._(
                    "Select %(qty)s serial numbers for %(product)s.", qty=qty, product=product.display_name))
        elif product.tracking == 'lot' and len(lots) != 1:
            raise UserError(self.env._("Select one lot for %(product)s.", product=product.display_name))
        if mode == 'return' and lots - sol._om_rental_out_lots():
            raise UserError(self.env._(
                "%(lots)s of %(product)s were not picked up with this order.",
                lots=", ".join((lots - sol._om_rental_out_lots()).mapped('name')), product=product.display_name))

        Quant = self.env['stock.quant'].sudo()
        line_vals = []
        if product.tracking == 'serial':
            for lot in lots:
                if product.uom_id.compare(Quant._get_available_quantity(product, source, lot_id=lot), 1) < 0:
                    raise UserError(self.env._(
                        "Serial number %(lot)s is not available in %(location)s.",
                        lot=lot.name, location=source.display_name))
                line_vals.append({'lot_id': lot.id, 'quantity': 1.0})
        else:
            lot = lots[:1]
            available = Quant._get_available_quantity(product, source, lot_id=lot or None)
            if product.uom_id.compare(available, qty) < 0:
                raise UserError(self.env._(
                    "Only %(available)s %(uom)s of %(product)s are available in %(location)s.",
                    available=available, uom=product.uom_id.name, product=product.display_name,
                    location=source.display_name))
            line_vals.append({'lot_id': lot.id, 'quantity': qty})

        order = sol.order_id
        company = order.company_id
        move = self.env['stock.move'].sudo().create({
            'product_id': product.id,
            'uom_id': product.uom_id.id,
            'product_uom_qty': qty,
            'company_id': company.id,
            'state': 'confirmed',
            'location_id': source.id,
            'location_dest_id': dest.id,
            'origin': order.name,
            'partner_id': order.partner_shipping_id.id,
            'rental_line_id': sol.id,
            'picked': True,
            'move_line_ids': [Command.create(dict(vals, **{
                'product_id': product.id,
                'uom_id': product.uom_id.id,
                'location_id': source.id,
                'location_dest_id': dest.id,
                'company_id': company.id,
            })) for vals in line_vals],
        })
        move._action_done()
        if lots:
            field = 'rental_pickedup_lot_ids' if mode == 'pickup' else 'rental_returned_lot_ids'
            sol.write({field: [Command.link(lot.id) for lot in lots]})
