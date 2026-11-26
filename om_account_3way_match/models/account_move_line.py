from odoo import api, fields, models
from odoo.tools.sql import column_exists, create_column
from odoo.tools.float_utils import float_compare

MATCH_STATES = [
    ('matched', 'Matched'),
    ('waiting', 'Waiting for Receipt'),
    ('qty', 'Quantity Exception'),
    ('price', 'Price Exception'),
    ('none', 'Not Linked'),
]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    om_match_state = fields.Selection(
        MATCH_STATES, string='Match Status', compute='_compute_om_match_state', store=True,
        help="Matched: the billed quantity is received (or ordered, for a 2-way match) and the price is within the "
             "tolerance.\n"
             "Waiting for Receipt: more is billed than received so far.\n"
             "Quantity Exception: more is billed than ordered.\n"
             "Price Exception: the bill price is above the purchase order price beyond the tolerance.\n"
             "Not Linked: the line is not linked to a purchase order line.")
    om_ordered_qty = fields.Float(string='PO Ordered Qty', compute='_compute_om_match_values', digits='Product Unit')
    om_received_qty = fields.Float(string='PO Received Qty', compute='_compute_om_match_values', digits='Product Unit')
    om_billed_qty = fields.Float(
        string='PO Billed Qty', compute='_compute_om_match_values', digits='Product Unit',
        help="Quantity billed on this bill and on the other posted bills of the purchase order line, less refunds.")
    om_po_uom_id = fields.Many2one(related='purchase_line_id.uom_id', string='PO Unit')
    om_po_price_unit = fields.Monetary(
        string='PO Unit Price', compute='_compute_om_match_values', currency_field='currency_id',
        help="Net unit price of the purchase order line, in the currency of the bill and the unit of the order.")
    om_bill_price_unit = fields.Monetary(
        string='Bill Net Unit Price', compute='_compute_om_match_values', currency_field='currency_id',
        help="Net unit price of the bill line (after discount), in the unit of the purchase order.")
    om_two_way = fields.Boolean(
        string='2-Way Match', compute='_compute_om_match_values',
        help="The product is billed on ordered quantities: only the purchase order is matched, not the receipt.")

    def _auto_init(self):
        # created empty: only the vendor bill lines are computed, by the post init hook
        if not column_exists(self.env.cr, 'account_move_line', 'om_match_state'):
            create_column(self.env.cr, 'account_move_line', 'om_match_state', 'varchar')
        return super()._auto_init()

    def _om_match_values(self):
        """ Return the values of the match of the line with its purchase order line, or an empty dict. """
        self.ensure_one()
        pol = self.purchase_line_id
        move = self.move_id
        if not pol or move.move_type != 'in_invoice' or self.display_type != 'product':
            return {}
        company = move.company_id or self.env.company
        po_uom = pol.uom_id or pol.product_id.uom_id
        line_uom = self.product_uom_id or po_uom

        def to_po_uom(line):
            uom = line.product_uom_id or po_uom
            return uom._compute_quantity(line.quantity, po_uom, round=False) if uom and po_uom else line.quantity

        billed = 0.0
        for other in pol.invoice_lines:
            other_move = other.move_id
            if other_move._origin == move._origin or other_move.state != 'posted':
                continue
            if other_move.move_type == 'in_invoice':
                billed += to_po_uom(other)
            elif other_move.move_type == 'in_refund':
                billed -= to_po_uom(other)
        for line in move.invoice_line_ids:
            if line.purchase_line_id == pol and line.display_type == 'product':
                billed += to_po_uom(line)

        bill_net = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        if line_uom and po_uom and line_uom != po_uom:
            bill_net = line_uom._compute_price(bill_net, po_uom)
        po_net = pol.price_unit * (1 - (pol.discount or 0.0) / 100.0)
        currency = move.currency_id or company.currency_id
        po_currency = pol.currency_id or currency
        date = move.invoice_date or move.date or fields.Date.context_today(self)
        if po_currency != currency:
            po_net = po_currency._convert(po_net, currency, company, date)
        two_way = pol.product_id.purchase_method == 'purchase' and company.om_3way_ordered_policy == 'two_way'
        return {
            'ordered': pol.product_qty,
            'received': pol.qty_received,
            'billed': billed,
            'po_price': po_net,
            'bill_price': bill_net,
            'two_way': two_way,
            'currency': currency,
            'company': company,
            'date': date,
            'uom': po_uom,
        }

    @api.depends(
        'purchase_line_id', 'move_id.move_type', 'move_id.state', 'display_type', 'move_id.currency_id',
        'move_id.invoice_date', 'quantity', 'price_unit', 'discount', 'product_uom_id',
        'move_id.invoice_line_ids.quantity', 'move_id.invoice_line_ids.purchase_line_id',
        'move_id.invoice_line_ids.product_uom_id',
        'purchase_line_id.product_qty', 'purchase_line_id.qty_received', 'purchase_line_id.price_unit',
        'purchase_line_id.discount', 'purchase_line_id.uom_id', 'purchase_line_id.order_id.currency_id',
        'purchase_line_id.invoice_lines.quantity', 'purchase_line_id.invoice_lines.move_id.state',
        'purchase_line_id.product_id.purchase_method',
    )
    def _compute_om_match_state(self):
        for line in self:
            if line.move_id.move_type != 'in_invoice' or line.display_type != 'product':
                line.om_match_state = False
                continue
            values = line._om_match_values()
            if not values:
                line.om_match_state = 'none'
            elif line.purchase_line_id.is_downpayment or line.is_downpayment:
                line.om_match_state = 'matched'
            else:
                line.om_match_state = line._om_match_state_from_values(values)

    def _om_match_state_from_values(self, values):
        company = values['company']
        uom = values['uom']

        def compare(value1, value2):
            if uom:
                return uom.compare(value1, value2)
            return float_compare(value1, value2, precision_digits=self.env['decimal.precision'].precision_get('Product Unit'))

        qty_factor = 1 + (company.om_3way_qty_tol_percent or 0.0) / 100.0
        billed = values['billed']
        if compare(billed, values['ordered'] * qty_factor) > 0:
            return 'qty'
        currency = values['currency']
        allowed = values['po_price'] * (company.om_3way_price_tol_percent or 0.0) / 100.0
        if company.om_3way_price_tol_amount:
            allowed = max(allowed, company.currency_id._convert(
                company.om_3way_price_tol_amount, currency, company, values['date']))
        if currency.compare_amounts(values['bill_price'] - values['po_price'] - allowed, 0.0) > 0:
            return 'price'
        reference = values['ordered'] if values['two_way'] else values['received']
        if compare(billed, reference * qty_factor) > 0:
            return 'waiting'
        return 'matched'

    @api.depends('om_match_state', 'quantity', 'price_unit', 'purchase_line_id')
    def _compute_om_match_values(self):
        for line in self:
            values = line._om_match_values()
            line.om_ordered_qty = values.get('ordered', 0.0)
            line.om_received_qty = values.get('received', 0.0)
            line.om_billed_qty = values.get('billed', 0.0)
            line.om_po_price_unit = values.get('po_price', 0.0)
            line.om_bill_price_unit = values.get('bill_price', 0.0)
            line.om_two_way = values.get('two_way', False)
