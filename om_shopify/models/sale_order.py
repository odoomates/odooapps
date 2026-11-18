import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import queries

_logger = logging.getLogger(__name__)

PAID_STATUSES = ('PAID', 'PARTIALLY_REFUNDED')
PAYMENT_KINDS = ('SALE', 'CAPTURE')
RISKY = ('CANCEL', 'INVESTIGATE')
CANCEL_REASONS = [
    ('CUSTOMER', 'The customer wanted to cancel'),
    ('INVENTORY', 'Items unavailable'),
    ('FRAUD', 'Fraudulent order'),
    ('DECLINED', 'Payment declined'),
    ('STAFF', 'Staff error'),
    ('OTHER', 'Other'),
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    shopify_store_id = fields.Many2one('om.shopify.store', string='Shopify Store', readonly=True, index=True,
                                       copy=False)
    shopify_order_gid = fields.Char(string='Shopify ID', readonly=True, copy=False)
    shopify_order_name = fields.Char(string='Shopify Order', readonly=True, copy=False)
    shopify_financial_status = fields.Char(string='Shopify Payment Status', readonly=True, copy=False)
    shopify_fulfillment_status = fields.Char(string='Shopify Fulfillment Status', readonly=True, copy=False)
    shopify_gateway_id = fields.Many2one('om.shopify.gateway', string='Shopify Payment Method', readonly=True,
                                         copy=False)
    shopify_workflow_id = fields.Many2one('om.connector.order.workflow', string='Shopify Workflow', readonly=True,
                                          copy=False)
    shopify_source = fields.Char(string='Shopify Channel', readonly=True, copy=False)
    shopify_risk = fields.Selection([
        ('ACCEPT', 'Accept'), ('INVESTIGATE', 'Investigate'), ('CANCEL', 'Cancel'), ('NONE', 'None'),
    ], string='Shopify Risk', readonly=True, copy=False)
    shopify_risk_message = fields.Text(string='Risk Details', readonly=True, copy=False)
    shopify_on_hold = fields.Boolean(string='On Hold (Risk)', readonly=True, copy=False,
                                     help="The workflow waits: Shopify finds this order risky.")
    shopify_cancelled = fields.Boolean(string='Cancelled in Shopify', readonly=True, copy=False)
    shopify_refund_gids = fields.Text(string='Shopify Refunds Applied', readonly=True, copy=False,
                                      help="The Shopify refunds already applied to this order, one per line.")

    _shopify_order_unique = models.UniqueIndex(
        '(shopify_store_id, shopify_order_gid) WHERE shopify_order_gid IS NOT NULL',
        "A Shopify order is imported once per store.")

    def action_open_in_shopify(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'https://{self.shopify_store_id.shop_domain}/admin/orders/'
                   f'{self.shopify_order_gid.rsplit("/", 1)[-1]}',
            'target': 'new',
        }

    def action_shopify_release(self):
        """ The user checked the risky order: run its workflow. """
        for order in self.filtered('shopify_on_hold'):
            order.shopify_on_hold = False
            order.message_post(body=_("Released by %(user)s despite the risk.", user=self.env.user.name))
            order._shopify_sync_now()

    def action_shopify_cancel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Cancel in Shopify"),
            'res_model': 'om.shopify.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _shopify_sync_now(self):
        for order in self:
            self._shopify_sync_order(order.shopify_store_id, order.shopify_order_gid)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    @api.model
    def _connector_job_shopify_import_order(self, job):
        return self._shopify_sync_order(job.backend, job.payload['id'])

    @api.model
    def _connector_job_shopify_order_webhook(self, job):
        gid = job.payload.get('admin_graphql_api_id') or f"gid://shopify/Order/{job.payload['id']}"
        return self._shopify_sync_order(job.backend, gid)

    @api.model
    def _connector_job_shopify_refund_webhook(self, job):
        order_id = job.payload.get('order_id')
        if not order_id:
            return _("No order in this refund")
        return self._shopify_sync_order(job.backend, f"gid://shopify/Order/{order_id}")

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @api.model
    def _shopify_sync_order(self, store, gid):
        """ Import the Shopify order ``gid``, or apply its news (edited, paid, fulfilled, refunded,
        cancelled) to the sale order imported before. Gives the sale order, or a text when skipped. """
        data = store._shopify_execute(store._shopify_query(queries.ORDER), {'id': gid}).get('order')
        if not data:
            return _("Order %(id)s does not exist anymore", id=gid)
        order = self.search([('shopify_store_id', '=', store.id), ('shopify_order_gid', '=', gid)], limit=1)
        if order:
            store._shopify_apply_metafields('order', order, data.get('metafields'))
            return order._shopify_update(data)
        if data.get('test') and not store.order_import_test:
            return _("%(name)s is a test order: skipped", name=data['name'])
        if data.get('cancelledAt'):
            return _("%(name)s is cancelled: skipped", name=data['name'])
        if (data.get('sourceName') or '').lower() == 'pos' and not store.order_import_pos:
            return _("%(name)s is a point of sale order: skipped", name=data['name'])
        if (data['lineItems'].get('pageInfo') or {}).get('hasNextPage'):
            raise UserError(_("%(name)s has more than 250 lines: import it by hand.", name=data['name']))
        order = self._shopify_create(store, data)
        store._shopify_apply_metafields('order', order, data.get('metafields'))
        order._shopify_process(data)
        return order

    @api.model
    def _shopify_money_key(self, store, data):
        """ ``presentmentMoney`` (the currency the customer paid in) or ``shopMoney``. """
        if store.order_currency == 'customer' and data.get('presentmentCurrencyCode') \
                and data['presentmentCurrencyCode'] != data.get('currencyCode'):
            return 'presentmentMoney'
        return 'shopMoney'

    @api.model
    def _shopify_rule_values(self, store, data, gateway):
        """ ``(workflow, warehouse)`` of an order, from the rules, the payment method and the store. """
        workflow = warehouse = None
        for rule in store.order_rule_ids:
            if rule._matches(data, gateway):
                workflow = workflow or rule.workflow_id or None
                warehouse = warehouse or rule.warehouse_id or None
        if not warehouse and store.order_warehouse_from_location:
            assigned = {((fo.get('assignedLocation') or {}).get('location') or {}).get('id')
                        for fo in (data.get('fulfillmentOrders') or {}).get('nodes') or []}
            location = store.location_ids.filtered(lambda l: l.shopify_gid in assigned and l.warehouse_id)[:1]
            warehouse = location.warehouse_id or None
        return (workflow or gateway.workflow_id or store.workflow_id,
                warehouse or store.warehouse_id)

    @api.model
    def _shopify_create(self, store, data):
        money = self._shopify_money_key(store, data)
        b2b = self._shopify_b2b_values(store, data)
        if (data.get('sourceName') or '').lower() == 'pos' and not data.get('customer') and store.pos_partner_id:
            partner = invoice = delivery = store.pos_partner_id
        elif b2b:
            partner, invoice, delivery = b2b['partner'], b2b['invoice'], b2b['delivery']
        else:
            partner, invoice, delivery = self.env['om.shopify.customer']._shopify_partner(store, data)
        gateway = self.env['om.shopify.gateway']._shopify_get(store, self._shopify_main_gateway(data))
        workflow, warehouse = self._shopify_rule_values(store, data, gateway)
        vals = {
            'partner_id': partner.id,
            'partner_invoice_id': invoice.id,
            'partner_shipping_id': delivery.id,
            'company_id': store.company_id.id,
            'warehouse_id': warehouse.id,
            'date_order': fields.Datetime.to_datetime(
                (data.get('processedAt') or data['createdAt'])[:19].replace('T', ' ')),
            'client_order_ref': data['name'],
            'origin': data['name'],
            'note': data.get('note') or False,
            'shopify_store_id': store.id,
            'shopify_order_gid': data['id'],
            'shopify_order_name': data['name'],
            'shopify_financial_status': data.get('displayFinancialStatus'),
            'shopify_fulfillment_status': data.get('displayFulfillmentStatus'),
            'shopify_gateway_id': gateway.id,
            'shopify_workflow_id': workflow.id,
            'shopify_source': data.get('sourceName'),
            'team_id': store.team_id.id or False,
            'user_id': store.user_id.id or False,
        }
        if store.order_use_shopify_name:
            vals['name'] = f"{store.order_prefix or ''}{data['name']}"
        currency_code = data.get('presentmentCurrencyCode') if money == 'presentmentMoney' else data.get('currencyCode')
        pricelist = store._shopify_pricelist(currency_code)
        if pricelist:
            vals['pricelist_id'] = pricelist.id
        if tags := self._connector_tags(data.get('tags')):
            vals['tag_ids'] = [fields.Command.set(tags.ids)]
        vals.update(self._shopify_risk_vals(data))
        if b2b and b2b.get('payment_term'):
            vals['payment_term_id'] = b2b['payment_term'].id
        if b2b and b2b.get('fiscal_position'):
            vals['fiscal_position_id'] = b2b['fiscal_position'].id
        order = self.with_company(store.company_id).create(vals)
        order.order_line = [fields.Command.create(line) for line in self._shopify_line_vals(store, data, money)]
        order._shopify_check_total(data, money)
        if order.shopify_on_hold:
            order._shopify_hold_activity()
        return order

    @api.model
    def _shopify_b2b_values(self, store, data):
        """ The company, addresses, payment terms and fiscal position of a B2B order, or {}. """
        entity = data.get('purchasingEntity') or {}
        company_gid = (entity.get('company') or {}).get('id')
        if not store.b2b_import or not company_gid:
            return {}
        Company = self.env['om.shopify.company']
        if not Company._connector_find(store, company_gid):
            Company._shopify_import_company(store, company_gid)
        company = Company._connector_find(store, company_gid)
        location = self.env['om.shopify.company.location']._connector_find(
            store, (entity.get('location') or {}).get('id') or '')
        if not company:
            return {}
        partner = company.partner_id
        contact = self.env['om.shopify.customer']._connector_find(
            store, (data.get('customer') or {}).get('id') or '').partner_id
        if contact and contact.commercial_partner_id == partner:
            partner = contact
        delivery = location.partner_id or partner
        if data.get('shippingAddress'):
            delivery = self.env['om.shopify.customer']._shopify_child(company.partner_id, 'delivery',
                                                                      data['shippingAddress'])
        return {
            'partner': partner,
            'invoice': location.invoice_partner_id or company.partner_id,
            'delivery': delivery,
            'payment_term': location.payment_term_id,
            'fiscal_position': store.b2b_tax_exempt_fiscal_position_id if location.tax_exempt else False,
        }

    @api.model
    def _shopify_risk_vals(self, data):
        risk = data.get('risk') or {}
        recommendation = risk.get('recommendation')
        facts = [fact.get('description') for assessment in risk.get('assessments') or []
                 for fact in assessment.get('facts') or [] if fact.get('description')]
        return {
            'shopify_risk': recommendation if recommendation in ('ACCEPT', 'INVESTIGATE', 'CANCEL', 'NONE') else False,
            'shopify_risk_message': '\n'.join(facts) or False,
            'shopify_on_hold': recommendation in RISKY,
        }

    def _shopify_hold_activity(self):
        self.ensure_one()
        self.activity_schedule(
            'mail.mail_activity_data_todo', user_id=(self.shopify_store_id.responsible_id or self.env.user).id,
            summary=_("Risky Shopify order"),
            note=_("Shopify recommends to %(action)s this order. Check it, then click Release or cancel it.",
                   action=dict(self._fields['shopify_risk'].selection).get(self.shopify_risk, '').lower()))

    @api.model
    def _shopify_main_gateway(self, data):
        names = [n for n in data.get('paymentGatewayNames') or [] if n != 'gift_card']
        return names[0] if names else (data.get('paymentGatewayNames') or ['manual'])[0]

    @api.model
    def _shopify_line_vals(self, store, data, money='shopMoney'):
        def amount(money_set):
            return float(((money_set or {}).get(money) or {}).get('amount') or 0.0)

        taxes_included = bool(data.get('taxesIncluded'))
        lines = []
        for item in data['lineItems']['nodes']:
            quantity = item.get('currentQuantity', item.get('quantity')) or 0
            if quantity <= 0:
                continue
            lines.append(self._shopify_product_line_vals(store, item, quantity, amount, taxes_included))
        for shipping in (data.get('shippingLines') or {}).get('nodes') or []:
            price = amount(shipping.get('originalPriceSet'))
            discount_amount = sum(amount(a.get('allocatedAmountSet')) for a in shipping.get('discountAllocations') or [])
            vals = {
                'product_id': store.shipping_product_id.id,
                'name': shipping.get('title') or store.shipping_product_id.name,
                'product_uom_qty': 1,
                'price_unit': price,
                'discount': self._connector_discount(price, discount_amount),
                'is_delivery': True,
            }
            if store.tax_mode == 'shopify':
                vals['tax_ids'] = [fields.Command.set(store._shopify_taxes(shipping.get('taxLines'), taxes_included).ids)]
            lines.append(vals)
        if tip := amount(data.get('totalTipReceivedSet')):
            lines.append({'product_id': store.tip_product_id.id, 'name': store.tip_product_id.name,
                          'product_uom_qty': 1, 'price_unit': tip, 'tax_ids': [fields.Command.clear()]})
        if duties := amount(data.get('currentTotalDutiesSet')):
            lines.append({'product_id': store.duties_product_id.id, 'name': store.duties_product_id.name,
                          'product_uom_qty': 1, 'price_unit': duties, 'tax_ids': [fields.Command.clear()]})
        return lines

    @api.model
    def _shopify_product_line_vals(self, store, item, quantity, amount, taxes_included):
        price = amount(item.get('originalUnitPriceSet'))
        product = store.gift_card_product_id if item.get('isGiftCard') else self._shopify_line_product(store, item)
        discount_amount = sum(amount(a.get('allocatedAmountSet')) for a in item.get('discountAllocations') or [])
        vals = {
            'product_id': product.id,
            'name': item.get('name') or product.display_name,
            'product_uom_qty': quantity,
            'price_unit': price,
            'discount': self._connector_discount(price * quantity, discount_amount),
            'shopify_line_gid': item['id'],
        }
        if store.tax_mode == 'shopify':
            vals['tax_ids'] = [fields.Command.set(store._shopify_taxes(item.get('taxLines'), taxes_included).ids)]
        return vals

    @api.model
    def _shopify_line_product(self, store, item):
        """ The Odoo product of an order line: the linked variant, imported when it is not yet,
        else the custom item product for the lines without a product in Shopify. """
        Variant = self.env['om.shopify.product']
        variant_gid = (item.get('variant') or {}).get('id')
        if variant_gid:
            binding = Variant._connector_find(store, variant_gid).filtered('active')
            if not binding and (item.get('product') or {}).get('id'):
                self.env['om.shopify.product.template']._shopify_import_product(store, item['product']['id'])
                binding = Variant._connector_find(store, variant_gid)
            if binding:
                return binding.product_id
        if item.get('sku'):
            match = Variant._shopify_match(store, {'sku': item['sku']})
            if match:
                return match
        return store.custom_product_id

    def _shopify_check_total(self, data, money='shopMoney'):
        """ Note on the order when its total is not the one of Shopify. """
        self.ensure_one()
        total = float(((data.get('totalPriceSet') or {}).get(money) or {}).get('amount') or 0.0)
        self._connector_check_total(total, _("Shopify"))

    # ------------------------------------------------------------------
    # Workflow, payments, deliveries
    # ------------------------------------------------------------------

    def _shopify_workflow(self):
        self.ensure_one()
        return self.shopify_workflow_id or self.shopify_gateway_id.workflow_id or self.shopify_store_id.workflow_id

    def _shopify_process(self, data):
        """ Run the workflow, register the payments, deliver what is fulfilled, and import the refunds. """
        self.ensure_one()
        if self.shopify_on_hold or self.state == 'cancel':
            return
        workflow = self._shopify_workflow()
        if not workflow:
            return
        date_order = self.date_order
        workflow._connector_process(self, paid=False)
        if self.date_order != date_order:
            # confirming dates the order of today: it keeps the date of Shopify
            self.date_order = date_order
        if data.get('displayFinancialStatus') in PAID_STATUSES or self._shopify_payments(data):
            self._shopify_register_payments(data, workflow)
        if self.state == 'sale' and data.get('displayFulfillmentStatus') == 'FULFILLED' \
                and self.shopify_store_id.order_deliver_fulfilled:
            self._shopify_deliver()
        self._shopify_import_refunds(data)

    @api.model
    def _shopify_payments(self, data, money='shopMoney'):
        """ ``{gateway: amount}`` received for the order, refunds apart. """
        paid = defaultdict(float)
        for transaction in data.get('transactions') or []:
            if transaction.get('status') == 'SUCCESS' and transaction.get('kind') in PAYMENT_KINDS:
                paid[transaction.get('gateway') or 'manual'] += float(
                    ((transaction.get('amountSet') or {}).get(money) or {}).get('amount') or 0.0)
        return dict(paid)

    def _shopify_register_payments(self, data, workflow):
        """ One payment per payment method of the order, in the journal of its workflow. """
        self.ensure_one()
        if not workflow.register_payment:
            return
        money = self._shopify_money_key(self.shopify_store_id, data)
        payments = self._shopify_payments(data, money)
        if len(payments) <= 1:
            if data.get('displayFinancialStatus') in PAID_STATUSES:
                gateway_name = next(iter(payments), None)
                journal = self._shopify_gateway_journal(gateway_name, workflow)
                workflow._connector_register_payment(self, journal=journal)
            return
        invoices = self.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
        already = sum(invoices.mapped(lambda m: m.amount_total - m.amount_residual)) \
            + workflow._connector_pending_payments(invoices)
        for gateway_name, amount in sorted(payments.items()):
            take = min(amount, already)
            already -= take
            workflow._connector_register_payment(self, amount=amount - take,
                                                 journal=self._shopify_gateway_journal(gateway_name, workflow))

    def _shopify_gateway_journal(self, gateway_name, workflow):
        if not gateway_name:
            return workflow.journal_id
        gateway = self.env['om.shopify.gateway']._shopify_get(self.shopify_store_id, gateway_name)
        return gateway.workflow_id.journal_id or workflow.journal_id

    def _shopify_invoice_delivered(self):
        """ After a delivery: invoice the products invoiced on delivered quantities, and register
        their payment when Shopify says the order is paid. """
        for order in self.filtered(lambda o: o.state == 'sale' and not o.shopify_on_hold):
            workflow = order._shopify_workflow()
            if not workflow or not workflow.create_invoice or order.invoice_status != 'to invoice':
                continue
            invoices = order._create_invoices()
            if workflow.post_invoice:
                invoices.action_post()
                if workflow.register_payment and order.shopify_financial_status in PAID_STATUSES:
                    workflow._connector_register_payment(
                        order, journal=order._shopify_gateway_journal(order.shopify_gateway_id.name, workflow))

    def _shopify_deliver(self):
        """ The order was fulfilled in Shopify before it reached Odoo: its deliveries are done. """
        self.ensure_one()
        if self._connector_deliver({'om_shopify_no_fulfill': True}):
            self._shopify_invoice_delivered()

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _shopify_update(self, data):
        """ Apply the news of a Shopify order to the sale order imported before. """
        self.ensure_one()
        vals = {
            'shopify_financial_status': data.get('displayFinancialStatus'),
            'shopify_fulfillment_status': data.get('displayFulfillmentStatus'),
        }
        if data.get('risk') and not self.shopify_risk:
            vals.update({k: v for k, v in self._shopify_risk_vals(data).items() if k != 'shopify_on_hold'})
        self.write(vals)
        if data.get('cancelledAt'):
            if self.state != 'cancel':
                self._shopify_cancel(data)
            self._shopify_import_refunds(data)
            return self
        if self.state == 'cancel':
            return self
        if self.shopify_store_id.order_sync_edits:
            self._shopify_apply_edits(data)
        self._shopify_process(data)
        return self

    def _shopify_apply_edits(self, data):
        """ Lines added, removed or changed in Shopify after the import, while nothing is delivered
        or invoiced in Odoo yet. """
        self.ensure_one()
        if self.invoice_ids.filtered(lambda m: m.state == 'posted') or \
                self.picking_ids.filtered(lambda p: p.state == 'done'):
            return
        store = self.shopify_store_id
        money = self._shopify_money_key(store, data)

        def amount(money_set):
            return float(((money_set or {}).get(money) or {}).get('amount') or 0.0)

        lines = {line.shopify_line_gid: line for line in self.order_line if line.shopify_line_gid}
        commands, changes = [], []
        for item in data['lineItems']['nodes']:
            quantity = item.get('currentQuantity', item.get('quantity')) or 0
            line = lines.get(item['id'])
            if line:
                if line.product_uom_qty != quantity:
                    changes.append(_("%(product)s: %(old)s → %(new)s", product=line.name,
                                     old=line.product_uom_qty, new=quantity))
                    commands.append(fields.Command.update(line.id, {'product_uom_qty': quantity}))
            elif quantity > 0:
                vals = self._shopify_product_line_vals(store, item, quantity, amount, bool(data.get('taxesIncluded')))
                changes.append(_("%(product)s: added (%(qty)s)", product=vals['name'], qty=quantity))
                commands.append(fields.Command.create(vals))
        if commands:
            self.order_line = commands
            self.message_post(body=_("Edited in Shopify: %(changes)s", changes='; '.join(changes)))

    def _shopify_cancel(self, data):
        self.ensure_one()
        self.shopify_cancelled = True
        delivered = self.picking_ids.filtered(lambda p: p.state == 'done')
        posted = self.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type == 'out_invoice')
        reason = data.get('cancelReason') or _("no reason")
        if delivered or posted:
            self.message_post(body=_(
                "This order was cancelled in Shopify (%(reason)s), but it is already delivered or invoiced in Odoo: "
                "its refunds are imported as credit notes; return the goods by hand.", reason=reason))
            return
        self.invoice_ids.filtered(lambda m: m.state == 'draft').button_cancel()
        self.with_context(disable_cancel_warning=True).action_cancel()
        self.message_post(body=_("Cancelled in Shopify (%(reason)s).", reason=reason))

    # ------------------------------------------------------------------
    # Refunds from Shopify
    # ------------------------------------------------------------------

    def _shopify_import_refunds(self, data):
        """ A credit note for each refund of Shopify not imported yet, paid back in the journal of the
        payment method; and a return of the products Shopify restocked, when asked. """
        self.ensure_one()
        store = self.shopify_store_id
        if not store.refund_import:
            return
        known = set((self.shopify_refund_gids or '').split())
        known |= set(self.env['account.move'].search([('shopify_store_id', '=', store.id),
                                                      ('shopify_refund_gid', '!=', False)]).mapped('shopify_refund_gid'))
        money = self._shopify_money_key(store, data)
        for refund in data.get('refunds') or []:
            if refund['id'] in known:
                continue
            self._shopify_credit_note(refund, money)
            self._shopify_reduce_refunded(refund, data)
            if store.refund_create_return:
                self._shopify_return(refund)
            known.add(refund['id'])
            self.shopify_refund_gids = '\n'.join(filter(None, [self.shopify_refund_gids, refund['id']]))

    def _shopify_credit_note(self, refund, money):
        self.ensure_one()
        store = self.shopify_store_id

        def amount(money_set):
            return float(((money_set or {}).get(money) or {}).get('amount') or 0.0)

        total = amount(refund.get('totalRefundedSet'))
        if not total:
            return self.env['account.move']
        if not self.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'):
            self.message_post(body=_("Shopify refunded %(amount)s before this order was invoiced: the refunded "
                                     "quantities leave the order, no credit note is needed.",
                                     amount=self.currency_id.format(total)))
            return self.env['account.move']
        lines_by_gid = {line.shopify_line_gid: line for line in self.order_line if line.shopify_line_gid}
        lines = []
        for refund_line in (refund.get('refundLineItems') or {}).get('nodes') or []:
            sale_line = lines_by_gid.get((refund_line.get('lineItem') or {}).get('id'))
            if sale_line:
                lines.append((sale_line, refund_line.get('quantity') or 0))
        shipping = sum(amount(s.get('subtotalAmountSet'))
                       for s in (refund.get('refundShippingLines') or {}).get('nodes') or [])
        credit_note = self._connector_credit_note(
            lines, total, _("Shopify refund %(order)s", order=self.shopify_order_name),
            shipping=shipping, shipping_product=store.shipping_product_id,
            adjustment_product=store.refund_adjustment_product_id, narration=refund.get('note') or False,
            extra_vals={'shopify_store_id': store.id, 'shopify_refund_gid': refund['id']})
        workflow = self._shopify_workflow()
        if workflow and workflow.register_payment:
            for transaction in (refund.get('transactions') or {}).get('nodes') or []:
                if transaction.get('status') == 'SUCCESS' and transaction.get('kind') == 'REFUND':
                    workflow._connector_refund_payment(
                        credit_note, amount=amount(transaction.get('amountSet')),
                        journal=self._shopify_gateway_journal(transaction.get('gateway'), workflow))
        self.message_post(body=_("Refund of Shopify imported: %(move)s.", move=credit_note._get_html_link()))
        return credit_note

    def _shopify_reduce_refunded(self, refund, data):
        """ The refunded lines get the quantity left in Shopify (never less than delivered), so that
        the order is not invoiced again for what was refunded. """
        self.ensure_one()
        current = {item['id']: item.get('currentQuantity', item.get('quantity')) or 0
                   for item in data['lineItems']['nodes']}
        lines_by_gid = {line.shopify_line_gid: line for line in self.order_line if line.shopify_line_gid}
        for refund_line in (refund.get('refundLineItems') or {}).get('nodes') or []:
            gid = (refund_line.get('lineItem') or {}).get('id')
            line = lines_by_gid.get(gid)
            if line and gid in current:
                new_qty = max(current[gid], line.qty_delivered)
                if new_qty < line.product_uom_qty:
                    line.product_uom_qty = new_qty

    def _shopify_return(self, refund):
        """ Return to stock the products Shopify restocked with this refund. """
        self.ensure_one()
        lines_by_gid = {line.shopify_line_gid: line for line in self.order_line if line.shopify_line_gid}
        quantities = defaultdict(float)
        for refund_line in (refund.get('refundLineItems') or {}).get('nodes') or []:
            sale_line = lines_by_gid.get((refund_line.get('lineItem') or {}).get('id'))
            if sale_line and refund_line.get('restockType') == 'RETURN' and refund_line.get('quantity'):
                quantities[sale_line] += refund_line['quantity']
        return self._connector_return(quantities, validate=self.shopify_store_id.refund_validate_return,
                                      context={'om_shopify_no_fulfill': True})


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    shopify_line_gid = fields.Char(string='Shopify Line ID', readonly=True, copy=False)
