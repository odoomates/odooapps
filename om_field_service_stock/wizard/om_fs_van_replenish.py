from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class OmFsVanReplenish(models.TransientModel):
    _name = 'om.fs.van.replenish'
    _description = "Replenish a Technician Van"

    employee_id = fields.Many2one('hr.employee', string="Technician", required=True)
    van_location_id = fields.Many2one(related='employee_id.van_location_id', string="Van")
    source_location_id = fields.Many2one(
        'stock.location', string="From", required=True, domain="[('usage', '=', 'internal')]",
        default=lambda self: self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1).lot_stock_id)
    days = fields.Integer(string="Parts Used in the Last", default=30,
                          help="Days of done jobs whose parts are proposed.")
    line_ids = fields.One2many('om.fs.van.replenish.line', 'wizard_id', string="Products")

    @api.onchange('employee_id', 'days')
    def _onchange_employee_id(self):
        """ Propose the parts taken from the van on the jobs done recently. """
        van = self.employee_id.van_location_id
        if not van:
            self.line_ids = [Command.clear()]
            return
        since = fields.Datetime.now() - timedelta(days=self.days or 30)
        parts = self.env['om.fs.job.part'].search([
            ('state', '=', 'done'), ('location_id', 'child_of', van.id),
            ('task_id.date_done', '>=', since),
        ])
        totals = {}
        for part in parts:
            key = (part.product_id, part.product_uom_id)
            totals[key] = totals.get(key, 0.0) + part.quantity
        self.line_ids = [Command.clear()] + [
            Command.create({'product_id': product.id, 'quantity': quantity, 'product_uom_id': uom.id})
            for (product, uom), quantity in totals.items()
        ]

    def action_confirm(self):
        self.ensure_one()
        van = self.employee_id.van_location_id
        lines = self.line_ids.filtered(lambda l: l.quantity > 0)
        if not van:
            raise UserError(self.env._("%s has no van stock location.", self.employee_id.name))
        if not lines:
            raise UserError(self.env._("Add the products to bring to the van."))
        warehouse = self.source_location_id.warehouse_id or van.warehouse_id
        picking_type = warehouse.int_type_id or self.env['stock.picking.type'].search([
            ('code', '=', 'internal'), ('company_id', '=', self.env.company.id)], limit=1)
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.source_location_id.id,
            'location_dest_id': van.id,
            'origin': self.env._("Van of %s", self.employee_id.name),
            'move_ids': [Command.create({
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'uom_id': line.product_uom_id.id,
                'location_id': self.source_location_id.id,
                'location_dest_id': van.id,
            }) for line in lines],
        })
        picking.action_confirm()
        picking.action_assign()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }


class OmFsVanReplenishLine(models.TransientModel):
    _name = 'om.fs.van.replenish.line'
    _description = "Product to Bring to a Van"

    wizard_id = fields.Many2one('om.fs.van.replenish', string="Wizard", required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Product", required=True,
                                 domain="[('type', '=', 'consu')]")
    quantity = fields.Float(string="Quantity", default=1.0, digits='Product Unit')
    product_uom_id = fields.Many2one('uom.uom', string="Unit", compute='_compute_product_uom_id', store=True, precompute=True,
                                     readonly=False, required=True)

    @api.depends('product_id')
    def _compute_product_uom_id(self):
        for line in self:
            if line.product_id and not line.product_uom_id:
                line.product_uom_id = line.product_id.uom_id
