from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain


class OmQualityCheck(models.Model):
    _inherit = 'om.quality.check'

    picking_id = fields.Many2one('stock.picking', string='Transfer', index='btree_not_null', check_company=True, readonly=True)
    picking_type_id = fields.Many2one(related='picking_id.picking_type_id', string='Operation Type', store=True)
    picking_code = fields.Selection(related='picking_id.picking_type_code', string='Operation Kind')
    picking_state = fields.Selection(related='picking_id.state', string='Transfer Status')
    move_id = fields.Many2one('stock.move', string='Stock Move', index='btree_not_null', readonly=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number', index='btree_not_null', check_company=True,
                             domain="[('product_id', '=', product_id)]")
    lot_name = fields.Char(string='Lot/Serial Name', help="Lot or serial number entered on a receipt before it exists.")
    quantity = fields.Float(string='Quantity', digits='Product Unit')
    product_uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    quarantine_location_id = fields.Many2one('stock.location', string='Quarantined In', readonly=True, copy=False)
    quarantine_picking_id = fields.Many2one('stock.picking', string='Quarantine Transfer', readonly=True, copy=False)
    return_picking_id = fields.Many2one('stock.picking', string='Return', readonly=True, copy=False)
    scrap_move_ids = fields.One2many('stock.move', 'om_quality_check_id', string='Scraps')
    disposition = fields.Selection(selection_add=[
        ('quarantine', 'Quarantined'),
        ('scrap', 'Scrapped'),
        ('return', 'Returned to vendor'),
    ], ondelete={'quarantine': 'set null', 'scrap': 'set null', 'return': 'set null'})

    def _compute_display_name(self):
        super()._compute_display_name()
        for check in self:
            lot = check.lot_id.name or check.lot_name
            if lot:
                check.display_name = f'{check.display_name} ({lot})'

    # ------------------------------------------------------------
    # Lots
    # ------------------------------------------------------------

    def _om_quality_link_lots(self):
        """ Once the transfer is done: the lot entered by name on a receipt exists, and a check
        of a move with a single lot gets that lot. """
        for check in self.filtered(lambda c: not c.lot_id and c.product_id.tracking != 'none'):
            if check.lot_name:
                lot = self.env['stock.lot'].search([
                    ('name', '=', check.lot_name), ('product_id', '=', check.product_id.id),
                    ('company_id', 'in', [check.company_id.id, False])], limit=1)
            else:
                lot = check._om_quality_move_lines().lot_id
            if len(lot) == 1:
                check.lot_id = lot
                check.alert_ids.filtered(lambda a: not a.lot_id).sudo().lot_id = lot

    def _om_quality_lots(self):
        """ The lots a check speaks for: its lot, or the lots of its done move. """
        self.ensure_one()
        if self.lot_id or self.lot_name:
            return self.lot_id
        if self.move_id.state == 'done':
            return self._om_quality_move_lines().lot_id
        return self.env['stock.lot']

    def _om_quality_apply_lot_state(self):
        """ The quality state of the lots follows their checks: a failed check puts the lot on
        hold, scrap or return rejects it, and the lot is released once nothing failed is left. """
        Check = self.env['om.quality.check']
        for check in self:
            for lot in check._om_quality_lots():
                if check.disposition in ('scrap', 'return'):
                    lot._om_quality_set_state('rejected', self.env._("Rejected after the check %s.", check.name))
                elif check.state == 'failed' and not check.is_overridden:
                    if lot.om_quality_state == 'ok':
                        lot._om_quality_set_state('hold', self.env._("Put on hold: the check %s failed.", check.name))
                elif lot.om_quality_state == 'hold':
                    open_failures = Check.sudo().search_count([
                        ('lot_id', '=', lot.id), ('state', '=', 'failed'), ('is_overridden', '=', False),
                        '|', ('disposition', '=', False), ('disposition', '=', 'quarantine')], limit=1)
                    retest_failed = Check.sudo().search_count([
                        ('lot_id', '=', lot.id), ('state', '=', 'failed'), ('disposition', '=', 'retest'),
                        ('retest_ids', '!=', False), ('retest_ids.state', '!=', 'passed')], limit=1)
                    if not open_failures and not retest_failed:
                        lot._om_quality_set_state('ok', self.env._("Released: the check %s passed.", check.name))

    def _on_failure(self):
        super()._on_failure()
        self._om_quality_apply_lot_state()

    def _on_pass(self):
        super()._on_pass()
        self._om_quality_apply_lot_state()

    def _do_override(self, reason):
        super()._do_override(reason)
        self._om_quality_apply_lot_state()

    def write(self, vals):
        res = super().write(vals)
        if 'lot_id' in vals and vals['lot_id']:
            self.filtered(lambda c: c.state == 'failed')._om_quality_apply_lot_state()
        return res

    def _prepare_alert_values(self):
        values = super()._prepare_alert_values()
        values.update({'lot_id': self.lot_id.id, 'picking_id': self.picking_id.id})
        return values

    def _prepare_retest_values(self):
        values = super()._prepare_retest_values()
        values.update({
            'picking_id': self.picking_id.id,
            'move_id': self.move_id.id,
            'lot_id': self.lot_id.id,
            'lot_name': self.lot_name,
            'quantity': self.quantity,
        })
        return values

    # ------------------------------------------------------------
    # What to do with the goods
    # ------------------------------------------------------------

    def _om_quality_check_decidable(self):
        self.ensure_one()
        if self.state != 'failed':
            raise UserError(self.env._("Only a failed check sends goods to quarantine, scrap or back to the vendor."))
        if self.disposition and self.disposition != 'quarantine':
            raise UserError(self.env._("The check %s is already decided.", self.name))
        if not self.picking_id:
            raise UserError(self.env._("The check %s is not on a transfer.", self.name))

    def _om_quality_move_lines(self):
        """ The move lines of the transfer with the checked goods. """
        self.ensure_one()
        lines = self.move_id.move_line_ids if self.move_id else self.picking_id.move_line_ids.filtered(
            lambda line: line.product_id == self.product_id)
        if self.lot_id:
            lines = lines.filtered(lambda line: line.lot_id == self.lot_id)
        elif self.lot_name:
            lines = lines.filtered(lambda line: line.lot_name == self.lot_name or line.lot_id.name == self.lot_name)
        return lines

    def _om_quality_warehouse(self):
        self.ensure_one()
        return self.picking_id.picking_type_id.warehouse_id or self.env['stock.warehouse'].search(
            [('company_id', '=', self.company_id.id)], limit=1)

    def _om_quality_checked_quantity(self, lines):
        self.ensure_one()
        quantity = sum(lines.mapped('quantity_product_uom'))
        return quantity or self.quantity or self.move_id.product_qty

    def _om_quality_internal_transfer(self, source, destination, quantity, name):
        """ A transfer of the checked goods, reserved on the checked lot. """
        self.ensure_one()
        warehouse = self._om_quality_warehouse()
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.int_type_id.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'origin': f'{self.name} - {self.picking_id.name}',
            'company_id': self.company_id.id,
            'move_ids': [Command.create({
                'product_id': self.product_id.id,
                'product_uom_qty': quantity,
                'uom_id': self.product_id.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
            })],
        })
        picking.action_confirm()
        move = picking.move_ids
        if self.lot_id:
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': self.product_id.id,
                'lot_id': self.lot_id.id,
                'quantity': quantity,
                'location_id': source.id,
                'location_dest_id': destination.id,
            })
            move._recompute_state()
        else:
            picking.with_context(om_quality_allow_held=True).action_assign()
        picking.message_post(body=Markup('%s %s') % (name, self._get_html_link()))
        return picking

    def action_om_quality_quarantine(self):
        self.ensure_one()
        self._om_quality_check_decidable()
        if self.disposition == 'quarantine':
            raise UserError(self.env._("The goods of the check %s are already in quarantine.", self.name))
        picking = self.picking_id
        location = self._om_quality_warehouse()._om_quality_quarantine_location()
        lines = self._om_quality_move_lines()
        result = False
        if picking.state != 'done' and picking.picking_type_code == 'incoming':
            if not lines:
                raise UserError(self.env._(
                    "Set the received quantity (and lot) of %s on the transfer first.", self.product_id.display_name))
            lines.location_dest_id = location
            picking.message_post(body=Markup('%s %s') % (
                self.env._("Sent to %s by the check", location.display_name), self._get_html_link()))
        else:
            if picking.state == 'done':
                source = lines[:1].location_dest_id or picking.location_dest_id
            else:
                source = lines[:1].location_id or picking.location_id
            quantity = self._om_quality_checked_quantity(lines)
            if picking.state != 'done':
                lines.unlink()
            transfer = self._om_quality_internal_transfer(
                source, location, quantity, self.env._("Quarantine of the goods of the check"))
            self.quarantine_picking_id = transfer
            result = {
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': transfer.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
            }
        self.write({'disposition': 'quarantine', 'quarantine_location_id': location.id})
        self._om_quality_lots()._om_quality_set_state('hold', self.env._("Quarantined by the check %s.", self.name))
        self.message_post(body=self.env._("Goods sent to quarantine: %s.", location.display_name))
        return result

    def action_om_quality_scrap(self):
        self.ensure_one()
        self._om_quality_check_decidable()
        picking = self.picking_id
        if picking.state != 'done' and picking.picking_type_code == 'incoming':
            raise UserError(self.env._("Validate the receipt first: goods not received yet cannot be scrapped."))
        lines = self._om_quality_move_lines()
        if self.quarantine_picking_id.state == 'done' or (self.quarantine_location_id and picking.state == 'done' and not self.quarantine_picking_id):
            location = self.quarantine_location_id
        elif picking.state == 'done':
            location = lines[:1].location_dest_id or picking.location_dest_id
        else:
            location = lines[:1].location_id or picking.location_id
        action = picking.action_scrap()
        action['context'].update({
            'default_product_id': self.product_id.id,
            'default_quantity': self._om_quality_checked_quantity(lines),
            'default_location_id': location.id,
            'default_om_quality_check_id': self.id,
            'product_ids': self.product_id.ids,
        })
        if self.lot_id:
            action['context']['default_lot_ids'] = [Command.set(self.lot_id.ids)]
            action['context']['lot_ids'] = self.lot_id.ids
        return action

    def action_om_quality_return(self):
        self.ensure_one()
        self._om_quality_check_decidable()
        picking = self.picking_id
        if picking.picking_type_code != 'incoming' or picking.state != 'done':
            raise UserError(self.env._("Only the goods of a validated receipt go back to the vendor."))
        lines = self._om_quality_move_lines()
        quantity = self._om_quality_checked_quantity(lines)
        returned = picking._create_return()
        moves = returned.move_ids
        keep = moves.filtered(lambda m: m.origin_returned_move_id == self.move_id) if self.move_id else \
            moves.filtered(lambda m: m.product_id == self.product_id)[:1]
        (moves - keep).unlink()
        keep.product_uom_qty = keep.product_id.uom_id._compute_quantity(quantity, keep.uom_id)
        if self.quarantine_location_id and not self.quarantine_picking_id:
            returned.location_id = self.quarantine_location_id
            keep.location_id = self.quarantine_location_id
        returned.action_confirm()
        if self.lot_id:
            keep.move_line_ids.unlink()
            self.env['stock.move.line'].create({
                'move_id': keep.id,
                'picking_id': returned.id,
                'product_id': self.product_id.id,
                'lot_id': self.lot_id.id,
                'quantity': quantity,
                'location_id': keep.location_id.id,
                'location_dest_id': keep.location_dest_id.id,
            })
            keep._recompute_state()
        else:
            returned.with_context(om_quality_allow_held=True).action_assign()
        self.write({'disposition': 'return', 'return_picking_id': returned.id})
        self._om_quality_apply_lot_state()
        self.message_post(body=self.env._("Return to the vendor: %s.", returned._get_html_link()))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': returned.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }

    def _om_quality_after_scrap(self):
        for check in self:
            check.disposition = 'scrap'
            check._om_quality_apply_lot_state()

    def _dialog_actions(self):
        actions = super()._dialog_actions()
        own = []
        if self.picking_id and self.state == 'failed' and (not self.disposition or self.disposition == 'quarantine') \
                and not self.is_overridden:
            picking = self.picking_id
            if self.disposition != 'quarantine':
                own.append(('action_om_quality_quarantine', self.env._('Quarantine'), 'warning'))
            if picking.state == 'done' or picking.picking_type_code != 'incoming':
                own.append(('action_om_quality_scrap', self.env._('Scrap'), 'danger'))
            if picking.state == 'done' and picking.picking_type_code == 'incoming':
                own.append(('action_om_quality_return', self.env._('Return to Vendor'), 'secondary'))
        return own + actions

    def _dialog_values(self):
        values = super()._dialog_values()
        extra = values['extra']
        lot = self.lot_id.name or self.lot_name
        if lot:
            extra.append([self.env._('Lot'), lot])
        if self.quantity:
            extra.append([self.env._('Quantity'), f'{self.quantity:g} {self.product_uom_id.name or ""}'.strip()])
        if self.quarantine_location_id:
            extra.append([self.env._('Quarantine'), self.quarantine_location_id.display_name])
        return values

    @api.model
    def _om_quality_lot_domain(self, product, lot=None, lot_name=None):
        domain = Domain('product_id', '=', product.id)
        if lot:
            return domain & (Domain('lot_id', '=', lot.id) | (Domain('lot_id', '=', False) & Domain('lot_name', '=', lot.name)))
        return domain & (Domain('lot_name', '=', lot_name) | Domain('lot_id.name', '=', lot_name))
