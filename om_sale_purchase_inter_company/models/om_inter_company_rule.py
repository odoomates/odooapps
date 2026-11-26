from odoo import fields, models
from odoo.fields import Domain


class OmInterCompanyRule(models.Model):
    _inherit = 'om.inter.company.rule'

    mirror_sale_orders = fields.Boolean(
        string="Sales Orders to Purchase Orders", default=True,
        help="Confirming a sales order to the other company creates its purchase order.")
    mirror_purchase_orders = fields.Boolean(
        string="Purchase Orders to Sales Orders",
        help="Confirming a purchase order from the other company creates its sales order.")
    order_state = fields.Selection(
        [('draft', "Quotation / Request for Quotation"), ('confirmed', "Confirmed")], string="Create Orders As",
        required=True, default='draft',
        help="Quotation / Request for Quotation: the receiving company confirms the order. Confirmed: it is "
             "confirmed at once, with its receipt or delivery.")
    keep_prices = fields.Boolean(
        string="Keep the Prices", default=True,
        help="The order created has the prices of the confirmed order. Without it, the prices come from the "
             "vendor pricelist or the pricelist of the receiving company.")
    salesperson_id = fields.Many2one(
        'res.users', string="Salesperson", domain=[('share', '=', False)],
        help="The salesperson of the sales orders created. Empty: the user the documents are created as.")
    buyer_id = fields.Many2one(
        'res.users', string="Buyer", domain=[('share', '=', False)],
        help="The buyer of the purchase orders created. Empty: the user the documents are created as.")
    sync_receipt = fields.Boolean(
        string="Validate the Receipt with the Delivery",
        help="Validating the delivery of the selling company validates the receipt of the buying company "
             "with the same quantities, lots and serial numbers.")
    target_warehouse_id = fields.Many2one(
        'stock.warehouse', string="Warehouse", domain="[('company_id', '=', target_company_id)]",
        help="The warehouse of the orders created in the other company. Empty: its first warehouse.")
    target_picking_type_id = fields.Many2one(
        'stock.picking.type', string="Receipt Type",
        domain="[('code', '=', 'incoming'), ('company_id', '=', target_company_id)]",
        help="The operation type of the purchase orders created in the other company. Empty: the receipts of "
             "the warehouse.")
    source_warehouse_id = fields.Many2one(
        'stock.warehouse', string="Warehouse of the Company", domain="[('company_id', '=', company_id)]",
        help="The warehouse of the orders created in the company. Empty: its first warehouse.")
    source_picking_type_id = fields.Many2one(
        'stock.picking.type', string="Receipt Type of the Company",
        domain="[('code', '=', 'incoming'), ('company_id', '=', company_id)]",
        help="The operation type of the purchase orders created in the company. Empty: the receipts of the "
             "warehouse.")

    def _om_ic_warehouse(self, company):
        self.ensure_one()
        warehouse = self.target_warehouse_id if self._om_ic_forward(company) else self.source_warehouse_id
        return warehouse or self.env['stock.warehouse'].sudo().search(Domain('company_id', '=', company.id), limit=1)

    def _om_ic_receipt_type(self, company):
        self.ensure_one()
        picking_type = self.target_picking_type_id if self._om_ic_forward(company) else self.source_picking_type_id
        return picking_type or self._om_ic_warehouse(company).in_type_id

    def action_om_ic_swap(self):
        res = super().action_om_ic_swap()
        for rule in self:
            rule.write({
                'target_warehouse_id': rule.source_warehouse_id.id,
                'source_warehouse_id': rule.target_warehouse_id.id,
                'target_picking_type_id': rule.source_picking_type_id.id,
                'source_picking_type_id': rule.target_picking_type_id.id,
            })
        return res
