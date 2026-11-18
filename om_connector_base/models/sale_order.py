from odoo import _, api, fields, models
from odoo.tools import float_round


class SaleOrder(models.Model):
    """ Helpers shared by the connectors for the orders they import. """
    _inherit = 'sale.order'

    @api.model
    def _connector_discount(self, amount, discount_amount):
        """ The discount percentage of ``discount_amount`` on ``amount``. """
        if not amount or not discount_amount:
            return 0.0
        return float_round(discount_amount / amount * 100.0, precision_digits=6)

    def _connector_check_total(self, total, source):
        """ A note on the order when its total is not ``total``, the total of the shop: the order is
        kept, the user checks it (a rounding, a tax set up differently). """
        self.ensure_one()
        if self.currency_id.compare_amounts(self.amount_total, total) != 0:
            self.message_post(body=_(
                "The total of this order in Odoo (%(odoo)s) is not the total in %(source)s (%(total)s): check its "
                "taxes and discounts.",
                odoo=self.currency_id.format(self.amount_total), source=source, total=self.currency_id.format(total)))

    def _connector_deliver(self, context=None):
        """ The order was shipped by the shop before it reached Odoo: its open deliveries are done.
        ``context``: added to the validation, e.g. to tell the connector not to ship it again.
        Gives the pickings validated. """
        self.ensure_one()
        pickings = self.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')
                                             and p.picking_type_code == 'outgoing')
        if not pickings:
            return pickings
        for move in pickings.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            move.quantity = move.product_uom_qty
            move.picked = True
        pickings.with_context(skip_backorder=True, skip_sanity_check=True, **(context or {}))._action_done()
        return pickings

    def _connector_credit_note(self, lines, total, ref, *, shipping=0.0, shipping_product=None,
                               adjustment_product=None, narration=False, extra_vals=None):
        """ A posted credit note for a refund of the shop, on the posted invoice of the order.

        :param lines: ``[(sale order line, quantity)]``: the refunded products; only what was invoiced
            is credited on its line, the rest goes in the adjustment
        :param total: the amount refunded by the shop
        :param shipping: the refunded shipping, on ``shipping_product``, taxed as the delivery line
        :param adjustment_product: what the shop refunded besides the lines and the shipping
        :param extra_vals: other values of the credit note (the refund ID of the connector…)
        Gives the credit note, or an empty recordset when the order has no posted invoice. """
        self.ensure_one()
        invoice = self.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')[:1]
        if not invoice or not total:
            return self.env['account.move']
        line_vals = []
        for sale_line, quantity in lines:
            quantity = min(quantity, sale_line.qty_invoiced)
            if quantity <= 0:
                continue
            line_vals.append({
                'product_id': sale_line.product_id.id,
                'name': sale_line.name,
                'quantity': quantity,
                'price_unit': sale_line.price_unit,
                'discount': sale_line.discount,
                'tax_ids': [fields.Command.set(sale_line.tax_ids.ids)],
                'sale_line_ids': [fields.Command.link(sale_line.id)],
            })
        if shipping and shipping_product:
            delivery = self.order_line.filtered('is_delivery')[:1]
            line_vals.append({
                'product_id': shipping_product.id,
                'name': _("Shipping refund"),
                'quantity': 1,
                'price_unit': shipping,
                'tax_ids': [fields.Command.set(delivery.tax_ids.ids)] if delivery else [fields.Command.clear()],
                'sale_line_ids': [fields.Command.link(delivery.id)] if delivery else [],
            })
        credit_note = self.env['account.move'].with_company(self.company_id).create({
            'move_type': 'out_refund',
            'partner_id': self.partner_invoice_id.id,
            'invoice_origin': self.name,
            'ref': ref,
            'reversed_entry_id': invoice.id,
            'currency_id': self.currency_id.id,
            'journal_id': invoice.journal_id.id,
            'narration': narration,
            'invoice_line_ids': [fields.Command.create(vals) for vals in line_vals],
            **(extra_vals or {}),
        })
        difference = self.currency_id.round(total - credit_note.amount_total)
        if not self.currency_id.is_zero(difference) and adjustment_product:
            credit_note.invoice_line_ids = [fields.Command.create({
                'product_id': adjustment_product.id,
                'name': _("Refund adjustment"),
                'quantity': 1,
                'price_unit': difference,
                'tax_ids': [fields.Command.clear()],
            })]
        credit_note.action_post()
        return credit_note

    def _connector_return(self, quantities, validate=False, context=None):
        """ Return to stock the products of the order shipped by its first done delivery.

        :param quantities: ``{sale order line: quantity}`` to return
        :param validate: validate the return at once
        :param context: added to the validation
        Gives the return, or None when there is nothing to return. """
        self.ensure_one()
        quantities = {line: qty for line, qty in quantities.items() if qty > 0}
        picking = self.picking_ids.filtered(lambda p: p.state == 'done' and p.picking_type_code == 'outgoing')[:1]
        if not quantities or not picking:
            return None
        returned = picking._create_return()
        left = dict(quantities)
        for move in returned.move_ids:
            origin = move.origin_returned_move_id
            wanted = min(left.get(origin.sale_line_id, 0.0), origin.quantity)
            if wanted > 0:
                move.product_uom_qty = wanted
                left[origin.sale_line_id] -= wanted
            else:
                move.unlink()
        if not returned.move_ids:
            returned.unlink()
            return None
        returned.action_confirm()
        returned.action_assign()
        if validate:
            for move in returned.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            returned.with_context(skip_backorder=True, **(context or {}))._action_done()
        return returned

    @api.model
    def _connector_tags(self, names):
        """ The sales tags named ``names``, found or created. """
        Tag = self.env['crm.tag']
        tags = Tag.browse()
        for name in {n.strip() for n in names or [] if n and n.strip()}:
            tags |= Tag.search([('name', '=', name)], limit=1) or Tag.create({'name': name})
        return tags
