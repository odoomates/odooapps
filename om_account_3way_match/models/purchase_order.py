from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    om_bill_control = fields.Selection(
        [('nothing', 'Nothing Billed'),
         ('to_bill', 'Received, Not Billed'),
         ('matched', 'Billed = Received'),
         ('waiting', 'Billed, Not Received'),
         ('over_billed', 'Billed over Ordered')],
        string='Bill Control', compute='_compute_om_bill_control',
        help="Billed against received quantities of the order lines (2-way products: against ordered quantities).")
    om_bill_exception_count = fields.Integer(string='Bills to Check', compute='_compute_om_bill_control')

    @api.depends('state', 'order_line.qty_received', 'order_line.qty_invoiced', 'order_line.product_qty',
                 'order_line.invoice_lines.move_id.om_release_state')
    def _compute_om_bill_control(self):
        for order in self:
            bills = order.order_line.invoice_lines.move_id.filtered(
                lambda move: move.state != 'cancel' and move.om_release_state in ('no', 'exception'))
            order.om_bill_exception_count = len(bills)
            if order.state != 'purchase':
                order.om_bill_control = False
                continue
            two_way = order.company_id.om_3way_ordered_policy == 'two_way'
            over_billed = waiting = to_bill = billed = False
            for line in order.order_line.filtered(lambda line: not line.display_type and not line.is_downpayment):
                uom = line.uom_id or line.product_id.uom_id
                if not uom:
                    continue
                if uom.compare(line.qty_invoiced, 0.0) > 0:
                    billed = True
                reference = line.qty_received
                if two_way and line.product_id.purchase_method == 'purchase':
                    reference = line.product_qty
                if uom.compare(line.qty_invoiced, line.product_qty) > 0:
                    over_billed = True
                elif uom.compare(line.qty_invoiced, reference) > 0:
                    waiting = True
                elif uom.compare(line.qty_invoiced, reference) < 0:
                    to_bill = True
            if over_billed:
                order.om_bill_control = 'over_billed'
            elif waiting:
                order.om_bill_control = 'waiting'
            elif to_bill:
                order.om_bill_control = 'to_bill'
            elif not billed:
                order.om_bill_control = 'nothing'
            else:
                order.om_bill_control = 'matched'

    def action_om_view_bills_to_check(self):
        self.ensure_one()
        bills = self.order_line.invoice_lines.move_id.filtered(
            lambda move: move.state != 'cancel' and move.om_release_state in ('no', 'exception'))
        action = self.env['ir.actions.actions']._for_xml_id('account.action_move_in_invoice_type')
        action['domain'] = [('id', 'in', bills.ids)]
        action['context'] = {'default_move_type': 'in_invoice', 'create': False}
        return action
