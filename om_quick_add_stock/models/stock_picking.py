from odoo import models
from odoo.fields import Domain

from odoo.addons.om_quick_add.models.quick_add_mixin import HISTORY_LINES


class StockPicking(models.Model):
    _name = 'stock.picking'
    _inherit = ['stock.picking', 'om.quick.add.mixin']

    _om_qa_line_field = 'move_ids'
    _om_qa_quantity_field = 'product_uom_qty'
    _om_qa_has_prices = False

    def _om_qa_editable(self):
        return self.state not in ('done', 'cancel')

    def _om_qa_partner(self):
        return self.partner_id.commercial_partner_id

    def _om_qa_product_domain(self):
        return super()._om_qa_product_domain() & Domain('type', '=', 'consu')

    def _om_qa_lines(self):
        return self.move_ids.filtered(lambda m: m.product_id and m.state != 'cancel' and not m.is_scrap)

    def _om_qa_line_data(self, move):
        picking = move.picking_id
        date = picking.date_done or picking.scheduled_date
        return {
            'product': move.product_id,
            'quantity': move.product_uom_qty,
            'uom': move.uom_id,
            'date': date and date.date(),
            'document': picking,
        }

    def _om_qa_new_line_vals(self, product, quantity, uom, price_unit, discount):
        return {
            'product_id': product.id,
            'product_uom_qty': quantity,
            'uom_id': (uom or product.uom_id).id,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'date': self.scheduled_date,
            # added after the confirmation: confirmed with the transfer
            'additional': self.state != 'draft',
        }

    def _om_qa_history_lines(self):
        return self.env['stock.move'].search([
            ('picking_id.partner_id', 'child_of', self._om_qa_partner().id),
            ('state', '=', 'done'),
            ('picking_code', '=', self.picking_type_code),
            ('picking_id', '!=', self.id or False),
            ('company_id', '=', self.company_id.id),
            ('product_id', '!=', False),
        ], order='id desc', limit=HISTORY_LINES)


class StockMove(models.Model):
    _name = 'stock.move'
    _inherit = ['stock.move', 'om.quick.add.line.mixin']

    _om_qa_document_model = 'stock.picking'
