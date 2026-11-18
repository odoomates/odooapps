import logging
from collections import defaultdict

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


def _float(value):
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    woo_store_id = fields.Many2one('om.woocommerce.store', string='WooCommerce Store', readonly=True, index=True,
                                   copy=False)
    woo_order_id = fields.Char(string='WooCommerce ID', readonly=True, copy=False)
    woo_order_number = fields.Char(string='WooCommerce Order', readonly=True, copy=False)
    woo_status = fields.Char(string='WooCommerce Status', readonly=True, copy=False)
    woo_paid = fields.Boolean(string='Paid in WooCommerce', readonly=True, copy=False)
    woo_gateway_id = fields.Many2one('om.woocommerce.gateway', string='WooCommerce Payment Method', readonly=True,
                                     copy=False)
    woo_workflow_id = fields.Many2one('om.connector.order.workflow', string='WooCommerce Workflow', readonly=True,
                                      copy=False)
    woo_created_via = fields.Char(string='Created Via', readonly=True, copy=False)
    woo_transaction_id = fields.Char(string='Transaction', readonly=True, copy=False)
    woo_cancelled = fields.Boolean(string='Cancelled in WooCommerce', readonly=True, copy=False)
    woo_coupon_ids = fields.Many2many('om.woocommerce.coupon', string='WooCommerce Coupons', readonly=True,
                                      copy=False)
    woo_refund_ids = fields.Text(string='WooCommerce Refunds Applied', readonly=True, copy=False,
                                 help="The WooCommerce refunds already applied to this order, one per line.")

    _woo_order_unique = models.UniqueIndex(
        '(woo_store_id, woo_order_id) WHERE woo_order_id IS NOT NULL',
        "A WooCommerce order is imported once per store.")

    def action_open_in_woocommerce(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'{self.woo_store_id.site_url}/wp-admin/post.php?post={self.woo_order_id}&action=edit',
            'target': 'new',
        }

    def action_woo_cancel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Cancel in WooCommerce"),
            'res_model': 'om.woocommerce.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_woo_sync(self):
        for order in self.filtered('woo_store_id'):
            self._woo_sync_order(order.woo_store_id, order.woo_order_id)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    @api.model
    def _connector_job_woo_import_order(self, job):
        return self._woo_sync_order(job.backend, job.payload['id'])

    @api.model
    def _connector_job_woo_order_webhook(self, job):
        payload = job.payload or {}
        # the webhook carries the whole order, as the REST API gives it
        return self._woo_sync_order(job.backend, payload['id'], data=payload if payload.get('line_items') is not None
                                    else None)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @api.model
    def _woo_sync_order(self, store, woo_id, data=None):
        """ Import the WooCommerce order ``woo_id``, or apply its news (paid, completed, refunded,
        cancelled) to the sale order imported before. Gives the sale order, or a text when skipped. """
        data = data or store._woo_get(f'orders/{woo_id}')
        if not data:
            return _("Order %(id)s does not exist anymore", id=woo_id)
        order = self.search([('woo_store_id', '=', store.id), ('woo_order_id', '=', str(data['id']))], limit=1)
        if order:
            return order._woo_update(data)
        if data.get('status') not in store.order_status_ids.mapped('code'):
            return _("#%(number)s is %(status)s: not imported", number=data.get('number'), status=data.get('status'))
        order = self._woo_create(store, data)
        order._woo_process(data)
        return order

    @api.model
    def _woo_paid(self, data):
        return bool(data.get('date_paid_gmt') or data.get('date_paid')) \
            and data.get('status') not in ('pending', 'failed', 'cancelled')

    @api.model
    def _woo_rule_values(self, store, data, gateway):
        """ ``(workflow, warehouse)`` of an order, from the rules, the payment method and the store. """
        workflow = warehouse = None
        for rule in store.order_rule_ids:
            if rule._matches(data, gateway):
                workflow = workflow or rule.workflow_id or None
                warehouse = warehouse or rule.warehouse_id or None
        return workflow or gateway.workflow_id or store.workflow_id, warehouse or store.warehouse_id

    @api.model
    def _woo_create(self, store, data):
        partner, invoice, delivery = self.env['om.woocommerce.customer']._woo_partner(store, data)
        gateway = self.env['om.woocommerce.gateway']._woo_get(store, data.get('payment_method'),
                                                              data.get('payment_method_title'))
        workflow, warehouse = self._woo_rule_values(store, data, gateway)
        number = str(data.get('number') or data['id'])
        vals = {
            'partner_id': partner.id,
            'partner_invoice_id': invoice.id,
            'partner_shipping_id': delivery.id,
            'company_id': store.company_id.id,
            'warehouse_id': warehouse.id,
            'date_order': store._woo_parse_date(data.get('date_created_gmt')) or fields.Datetime.now(),
            'client_order_ref': f'#{number}',
            'origin': f'#{number}',
            'note': data.get('customer_note') or False,
            'woo_store_id': store.id,
            'woo_order_id': str(data['id']),
            'woo_order_number': number,
            'woo_status': data.get('status'),
            'woo_paid': self._woo_paid(data),
            'woo_gateway_id': gateway.id,
            'woo_workflow_id': workflow.id,
            'woo_created_via': data.get('created_via') or False,
            'woo_transaction_id': data.get('transaction_id') or False,
            'team_id': store.team_id.id or False,
            'user_id': store.user_id.id or False,
        }
        if store.order_use_woo_number:
            vals['name'] = f"{store.order_prefix or ''}{number}"
        if pricelist := store._woo_pricelist(data.get('currency')):
            vals['pricelist_id'] = pricelist.id
        carriers = self._woo_shipping_methods(store, data).carrier_id
        if carriers:
            vals['carrier_id'] = carriers[0].id
        codes = [c['code'].strip().lower() for c in data.get('coupon_lines') or [] if c.get('code')]
        if tags := self._connector_tags([f'coupon:{code}' for code in codes]):
            vals['tag_ids'] = [fields.Command.set(tags.ids)]
        if codes and (coupons := self.env['om.woocommerce.coupon'].search(
                [('store_id', '=', store.id), ('code', 'in', codes)])):
            vals['woo_coupon_ids'] = [fields.Command.set(coupons.ids)]
        order = self.with_company(store.company_id).create(vals)
        order.order_line = [fields.Command.create(line) for line in self._woo_line_vals(store, data)]
        order._connector_check_total(_float(data.get('total')), _("WooCommerce"))
        store._woo_apply_meta('order', order, data.get('meta_data'))
        return order

    @api.model
    def _woo_shipping_methods(self, store, data):
        """ The shipping methods of the shipping lines of ``data``, in the order of the lines. """
        Shipping = self.env['om.woocommerce.shipping']
        methods = Shipping.browse()
        for shipping in data.get('shipping_lines') or []:
            methods += Shipping._woo_get(store, shipping.get('method_id'), shipping.get('method_title'))
        return methods

    @api.model
    def _woo_rates(self, store, data):
        """ ``{rate id: (percent, label)}`` of the tax lines of an order. """
        rates = {}
        for tax_line in data.get('tax_lines') or []:
            percent = tax_line.get('rate_percent')
            if percent in (None, '') and tax_line.get('rate_id'):
                percent = (store._woo_get(f"taxes/{tax_line['rate_id']}") or {}).get('rate')
            rates[tax_line.get('rate_id')] = (_float(percent), tax_line.get('label') or tax_line.get('rate_code'))
        return rates

    @api.model
    def _woo_line_taxes(self, store, item_taxes, rates, included):
        if store.tax_mode != 'woocommerce':
            return None
        used = [rates[tax['id']] for tax in item_taxes or []
                if tax.get('id') in rates and (_float(tax.get('total')) or _float(tax.get('subtotal')))]
        return [fields.Command.set(store._woo_taxes(used, included).ids)]

    @api.model
    def _woo_line_vals(self, store, data):
        """ The lines of the sale order of ``data``: products (discounts of the coupons included),
        shipping and fees. WooCommerce gives the amounts without taxes; shipping and fees never
        include taxes. """
        included = bool(data.get('prices_include_tax'))
        rates = self._woo_rates(store, data)
        lines = []
        for item in data.get('line_items') or []:
            vals = self._woo_product_line_vals(store, item, rates, included)
            if vals:
                lines.append(vals)
        methods = self._woo_shipping_methods(store, data)
        for shipping, method in zip(data.get('shipping_lines') or [], methods):
            product = method.carrier_id.product_id or store.shipping_product_id
            vals = {
                'product_id': product.id,
                'name': shipping.get('method_title') or product.name,
                'product_uom_qty': 1,
                'price_unit': _float(shipping.get('total')),
                'is_delivery': True,
                'woo_line_id': str(shipping['id']),
            }
            if taxes := self._woo_line_taxes(store, shipping.get('taxes'), rates, False):
                vals['tax_ids'] = taxes
            lines.append(vals)
        for fee in data.get('fee_lines') or []:
            vals = {
                'product_id': store.fee_product_id.id,
                'name': fee.get('name') or store.fee_product_id.name,
                'product_uom_qty': 1,
                'price_unit': _float(fee.get('total')),
                'woo_line_id': str(fee['id']),
            }
            if taxes := self._woo_line_taxes(store, fee.get('taxes'), rates, False):
                vals['tax_ids'] = taxes
            lines.append(vals)
        return lines

    @api.model
    def _woo_product_line_vals(self, store, item, rates, included):
        quantity = _float(item.get('quantity'))
        if quantity <= 0:
            return None
        subtotal, total = _float(item.get('subtotal')), _float(item.get('total'))
        if included:
            subtotal += _float(item.get('subtotal_tax'))
            total += _float(item.get('total_tax'))
        product = self._woo_line_product(store, item)
        vals = {
            'product_id': product.id,
            'name': item.get('name') or product.display_name,
            'product_uom_qty': quantity,
            'price_unit': subtotal / quantity,
            'discount': self._connector_discount(subtotal, subtotal - total),
            'woo_line_id': str(item['id']),
        }
        if taxes := self._woo_line_taxes(store, item.get('taxes'), rates, included):
            vals['tax_ids'] = taxes
        return vals

    @api.model
    def _woo_line_product(self, store, item):
        """ The Odoo product of an order line: the linked variant, imported when it is not yet, else
        the product with its SKU, else the product of unknown items. """
        Variant = self.env['om.woocommerce.product']
        woo_id = item.get('variation_id') or item.get('product_id')
        if woo_id:
            binding = Variant._connector_find(store, woo_id).filtered('active')
            if not binding and item.get('product_id'):
                self.env['om.woocommerce.product.template']._woo_import_product(store, item['product_id'])
                binding = Variant._connector_find(store, woo_id)
            if binding:
                return binding.product_id
        if item.get('sku'):
            match = Variant._woo_match(store, {'sku': item['sku']})
            if match:
                return match
        return store.custom_product_id

    # ------------------------------------------------------------------
    # Workflow, payments, deliveries
    # ------------------------------------------------------------------

    def _woo_workflow(self):
        self.ensure_one()
        return self.woo_workflow_id or self.woo_gateway_id.workflow_id or self.woo_store_id.workflow_id

    def _woo_journal(self, workflow):
        self.ensure_one()
        return self.woo_gateway_id.workflow_id.journal_id or workflow.journal_id

    def _woo_process(self, data):
        """ Run the workflow, register the payment, deliver a completed order, import the refunds. """
        self.ensure_one()
        if self.state == 'cancel':
            return
        workflow = self._woo_workflow()
        if not workflow:
            return
        date_order = self.date_order
        if not self.invoice_ids.filtered(lambda m: m.move_type == 'out_refund' and m.state == 'posted'):
            # after a credit note, what it credits is not invoiced again
            workflow._connector_process(self, paid=False)
        if self.date_order != date_order:
            # confirming dates the order of today: it keeps the date of WooCommerce
            self.date_order = date_order
        if self.woo_paid and workflow.register_payment:
            workflow._connector_register_payment(self, journal=self._woo_journal(workflow))
        if self.state == 'sale' and data.get('status') == 'completed' and self.woo_store_id.order_deliver_completed:
            if self._connector_deliver({'om_woocommerce_no_complete': True}):
                self._woo_invoice_delivered()
        self._woo_import_refunds(data)

    def _woo_invoice_delivered(self):
        """ After a delivery: invoice the products invoiced on delivered quantities, and register their
        payment when the order is paid. """
        for order in self.filtered(lambda o: o.state == 'sale'):
            workflow = order._woo_workflow()
            if not workflow or not workflow.create_invoice or order.invoice_status != 'to invoice':
                continue
            invoices = order._create_invoices()
            if workflow.post_invoice:
                invoices.action_post()
                if workflow.register_payment and order.woo_paid:
                    workflow._connector_register_payment(order, journal=order._woo_journal(workflow))

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _woo_update(self, data):
        """ Apply the news of a WooCommerce order to the sale order imported before. """
        self.ensure_one()
        self.write({'woo_status': data.get('status'), 'woo_paid': self._woo_paid(data) or self.woo_paid,
                    'woo_transaction_id': data.get('transaction_id') or self.woo_transaction_id})
        if data.get('status') in ('cancelled', 'failed'):
            if self.state != 'cancel':
                self._woo_cancel(data)
            self._woo_import_refunds(data)
            return self
        if self.state == 'cancel':
            return self
        self._woo_process(data)
        return self

    def _woo_cancel(self, data):
        self.ensure_one()
        self.woo_cancelled = True
        delivered = self.picking_ids.filtered(lambda p: p.state == 'done')
        posted = self.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type == 'out_invoice')
        if delivered or posted.filtered(lambda m: m.payment_state != 'not_paid'):
            self.message_post(body=_(
                "This order was cancelled in WooCommerce, but it is already delivered or paid in Odoo: its refunds "
                "are imported as credit notes; return the goods by hand."))
            return
        # an unpaid order (a bank transfer that never came): its invoice is cancelled with it
        posted.button_draft()
        self.invoice_ids.filtered(lambda m: m.state == 'draft').button_cancel()
        self.with_context(disable_cancel_warning=True).action_cancel()
        self.message_post(body=_("Cancelled in WooCommerce."))

    # ------------------------------------------------------------------
    # Refunds from WooCommerce
    # ------------------------------------------------------------------

    def _woo_import_refunds(self, data):
        """ A credit note for each refund of WooCommerce not imported yet, paid back in the journal of
        the payment method; and a return of the refunded products, when asked. """
        self.ensure_one()
        store = self.woo_store_id
        if not store.refund_import or not data.get('refunds'):
            return
        known = set((self.woo_refund_ids or '').split())
        known |= set(self.env['account.move'].search([('woo_store_id', '=', store.id),
                                                      ('woo_refund_id', '!=', False)]).mapped('woo_refund_id'))
        for summary in data.get('refunds') or []:
            refund_id = str(summary.get('id'))
            if refund_id in known:
                continue
            refund = store._woo_get(f"orders/{data['id']}/refunds/{refund_id}")
            if not refund:
                continue
            quantities = self._woo_refunded_quantities(refund)
            self._woo_credit_note(refund, quantities)
            self._woo_reduce_refunded(quantities)
            if store.refund_create_return:
                self._connector_return({line: qty for line, qty in quantities.items() if not line.is_delivery},
                                       validate=store.refund_validate_return,
                                       context={'om_woocommerce_no_complete': True})
            known.add(refund_id)
            self.woo_refund_ids = '\n'.join(filter(None, [self.woo_refund_ids, refund_id]))

    def _woo_refunded_quantities(self, refund):
        """ ``{sale order line: quantity}`` refunded by ``refund``. A refunded item gives the item of the
        order in its ``_refunded_item_id`` meta data, else it is found by its product. """
        self.ensure_one()
        lines_by_id = {line.woo_line_id: line for line in self.order_line if line.woo_line_id}
        products = {}
        for line in self.order_line.filtered(lambda l: l.woo_line_id and not l.is_delivery):
            products.setdefault(line.product_id, line)
        quantities = defaultdict(float)
        for item in refund.get('line_items') or []:
            original = next((str(meta.get('value')) for meta in item.get('meta_data') or []
                             if meta.get('key') == '_refunded_item_id'), None)
            line = lines_by_id.get(original)
            if not line:
                woo_id = item.get('variation_id') or item.get('product_id')
                binding = self.env['om.woocommerce.product']._connector_find(self.woo_store_id, woo_id) \
                    if woo_id else None
                line = products.get(binding.product_id) if binding else None
            if line:
                quantities[line] += abs(_float(item.get('quantity')))
        return quantities

    def _woo_credit_note(self, refund, quantities):
        self.ensure_one()
        store = self.woo_store_id
        total = abs(_float(refund.get('amount')))
        if not total:
            return self.env['account.move']
        if not self.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'):
            self.message_post(body=_("WooCommerce refunded %(amount)s before this order was invoiced: the refunded "
                                     "quantities leave the order, no credit note is needed.",
                                     amount=self.currency_id.format(total)))
            return self.env['account.move']
        shipping = sum(abs(_float(line.get('total'))) for line in refund.get('shipping_lines') or [])
        credit_note = self._connector_credit_note(
            [(line, qty) for line, qty in quantities.items() if not line.is_delivery], total,
            _("WooCommerce refund #%(number)s", number=self.woo_order_number),
            shipping=shipping, shipping_product=store.shipping_product_id,
            adjustment_product=store.refund_adjustment_product_id, narration=refund.get('reason') or False,
            extra_vals={'woo_store_id': store.id, 'woo_refund_id': str(refund['id'])})
        workflow = self._woo_workflow()
        if credit_note and workflow and workflow.register_payment and self.woo_paid:
            workflow._connector_refund_payment(credit_note, amount=total, journal=self._woo_journal(workflow))
        self.message_post(body=_("Refund of WooCommerce imported: %(move)s.", move=credit_note._get_html_link()))
        return credit_note

    def _woo_reduce_refunded(self, quantities):
        """ The refunded lines lose the refunded quantity (never less than delivered), so that the order
        is not invoiced again for what was refunded. """
        for line, quantity in quantities.items():
            if line.is_delivery or quantity <= 0:
                continue
            new_qty = max(line.product_uom_qty - quantity, line.qty_delivered)
            if new_qty < line.product_uom_qty:
                line.product_uom_qty = new_qty


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    woo_line_id = fields.Char(string='WooCommerce Line ID', readonly=True, copy=False)
