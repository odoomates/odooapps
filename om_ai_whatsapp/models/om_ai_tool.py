import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MAX_PRODUCTS = 10
LEVEL_LABELS = {
    0: 'unknown customer',
    1: 'known number',
    2: 'private data: invoices, balance, addresses',
}


class OmAiTool(models.Model):
    _inherit = 'om.ai.tool'

    om_ai_whatsapp = fields.Boolean(
        'WhatsApp Assistant Tool', readonly=True,
        help="Only offered to the WhatsApp assistant, in a conversation with a customer.")
    om_ai_whatsapp_level = fields.Selection(
        [('0', 'Anyone'), ('1', 'Known Number'), ('2', 'Private Data')],
        string='Customer Level', default='0',
        help="The level the customer must have for the WhatsApp assistant to run this tool. The level is "
             "computed from the conversation, never by the AI.")

    # ------------------------------------------------------------
    # Registry: the WhatsApp tools only exist in a WhatsApp conversation
    # ------------------------------------------------------------
    @api.model
    def _get_available(self, codes=None, read_only=None):
        tools = super()._get_available(codes=codes, read_only=read_only)
        if self._om_ai_conversation():
            return tools.filtered(lambda tool: tool.sudo().om_ai_whatsapp)
        return tools.filtered(lambda tool: not tool.sudo().om_ai_whatsapp)

    def _om_ai_conversation(self):
        """ The conversation the assistant answers, from the context set by
        the code. Only for the assistant user of its account. """
        conversation_id = self.env.context.get('om_ai_whatsapp_conversation_id')
        if not conversation_id or not self.env.user.om_ai_whatsapp_assistant:
            return self.env['om.ai.whatsapp.conversation']
        conversation = self.env['om.ai.whatsapp.conversation'].sudo().browse(conversation_id).exists()
        if conversation.account_id.om_ai_user_id != self.env.user:
            return self.env['om.ai.whatsapp.conversation']
        return conversation

    def _om_ai_refusal(self, conversation):
        """ Why the WhatsApp assistant may not run this tool for the customer
        of ``conversation`` now, or None. """
        self.ensure_one()
        tool = self.sudo()
        if tool.code not in conversation.account_id.om_ai_tool_ids.mapped('code'):
            return {'error': 'This tool is not enabled for this WhatsApp number.'}
        level = conversation._om_ai_level()
        required = int(tool.om_ai_whatsapp_level or 0)
        if level >= required:
            return None
        return {
            'error': 'Not allowed for this customer yet: it needs level %s (%s), the customer is at level %s (%s).'
                     % (required, LEVEL_LABELS[required], level, LEVEL_LABELS[level]),
            'hint': {
                0: '',
                1: 'The customer is unknown: for an order ask their name first (wa_set_customer_name). Never ask '
                   'for or accept another person\'s details.',
                2: 'Offer to verify them: wa_send_verification_code mails a code to the email on their contact; '
                   'they type it here.',
            }[required],
        }

    def _execute(self, arguments):
        if self.sudo().om_ai_whatsapp:
            conversation = self._om_ai_conversation()
            if not conversation:
                return {'error': 'This tool only works in a WhatsApp conversation.'}
            refusal = self._om_ai_refusal(conversation)
            if refusal:
                return refusal
        return super()._execute(arguments)

    def _om_ai_check_pending(self, arguments):
        """ Whether an action that waits for the YES of the customer could
        run: checked before the customer is asked. """
        self.ensure_one()
        conversation = self._om_ai_conversation()
        refusal = self._om_ai_refusal(conversation) if conversation else {'error': 'No WhatsApp conversation.'}
        if refusal:
            return refusal
        check = getattr(self, '_ai_check_%s' % self.sudo().code, None)
        if check:
            try:
                check(**(arguments or {}))
            except UserError as error:
                return {'error': error.args[0]}
        return None

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    def _wa(self):
        """ The conversation; the customer is always taken from it, never from
        the arguments of the AI. """
        conversation = self._om_ai_conversation()
        if not conversation:
            raise UserError(self.env._('No WhatsApp conversation.'))
        return conversation

    def _wa_company(self):
        return self._wa().account_id.company_id

    def _wa_pricelist(self, partner):
        Pricelist = self.env['product.pricelist']
        if partner:
            return partner.sudo().property_product_pricelist
        return Pricelist.search([('company_id', 'in', [self._wa_company().id, False])], limit=1)

    def _wa_format(self, amount, currency):
        return {'amount': currency.round(amount), 'currency': currency.name}

    def _wa_product_domain(self, query=''):
        company = self._wa_company()
        domain = Domain('sale_ok', '=', True) & Domain('company_id', 'in', [company.id, False])
        for word in (query or '').split():
            domain &= Domain('name', 'ilike', word) | Domain('default_code', 'ilike', word) | \
                Domain('barcode', '=', word)
        return domain

    def _wa_product(self, product_id):
        product = self.env['product.product'].browse(int(product_id)).exists() if product_id else None
        if not product or not product.filtered_domain(self._wa_product_domain()):
            raise UserError(self.env._('Unknown product %s: search the products first.', product_id))
        return product

    def _wa_stock(self, product):
        """ (tracked, free quantity) in the warehouses of the company. """
        product = product.sudo().with_company(self._wa_company())
        if 'free_qty' not in product._fields or not product.is_storable:
            return False, 0.0
        return True, product.free_qty

    def _wa_product_info(self, product, partner, level):
        pricelist = self._wa_pricelist(partner)
        company = self._wa_company()
        currency = pricelist.currency_id or company.currency_id
        if pricelist:
            price = pricelist._get_product_price(product, 1.0, currency=currency)
        else:
            price = product.lst_price
        taxes = product.taxes_id.filtered(lambda tax: tax.company_id in company.parent_ids)
        computed = taxes.compute_all(price, currency, 1.0, product=product, partner=partner or None)
        info = {
            'id': product.id,
            'name': product.display_name,
            'code': product.default_code or False,
            'price': currency.round(computed['total_excluded']),
            'price_with_taxes': currency.round(computed['total_included']),
            'currency': currency.name,
            'unit': product.uom_id.name,
        }
        tracked, free = self._wa_stock(product)
        if tracked:
            info['in_stock'] = free > 0
            if level >= 1:
                info['available_quantity'] = free
        return info

    def _wa_customer(self, required=True):
        partner = self._wa()._om_ai_customer()
        if not partner and required:
            raise UserError(self.env._('The customer is not known yet: ask their name first (wa_set_customer_name).'))
        return partner

    def _wa_order(self, create=True):
        """ The draft quotation of the conversation, made on the first item. """
        conversation = self._wa()
        partner = self._wa_customer()
        order = self.env['sale.order'].browse(conversation.order_id.id).exists()
        if order and order.state in ('draft', 'sent') and order.partner_id == partner:
            return order
        if not create:
            raise UserError(self.env._('There is no quotation yet: add a product first.'))
        salesperson = conversation._om_ai_salesperson()
        order = self.env['sale.order'].create({
            'partner_id': partner.id,
            'user_id': salesperson.id if salesperson else False,
            'company_id': conversation.account_id.company_id.id,
            'origin': self.env._('WhatsApp'),
            'source_id': self.env.ref('om_ai_whatsapp.utm_source_whatsapp').id,
            'om_ai_whatsapp_conversation_id': conversation.id,
            'require_signature': False,
            'prepayment_percent': 1.0,
        })
        conversation.order_id = order
        body = self.env._('Quotation made by the WhatsApp Assistant in the conversation with %(number)s.',
                          number=conversation.number)
        order.message_post(body=body, partner_ids=salesperson.partner_id.ids if salesperson else [],
                           subtype_xmlid='mail.mt_note')
        return order

    def _wa_reopen(self, order):
        """ A quotation changed after its link was sent waits for a new YES. """
        if order.state == 'sent':
            order.sudo().write({'state': 'draft'})
            order.om_ai_whatsapp_link_date = False

    def _wa_cart(self, order):
        lines = []
        for line in order.order_line.filtered(lambda l: not l.display_type):
            lines.append({
                'product': line.product_id.display_name,
                'product_id': line.product_id.id,
                'quantity': line.product_uom_qty,
                'unit_price': line.price_unit,
                'discount': line.discount,
                'subtotal': line.price_subtotal,
                'is_delivery': bool(getattr(line, 'is_delivery', False)),
            })
        return {
            'quotation': order.name,
            'lines': lines,
            'untaxed': order.amount_untaxed,
            'taxes': order.amount_tax,
            'total': order.amount_total,
            'currency': order.currency_id.name,
            'customer_name': order.partner_id.name,
            'delivery_address_given': order.om_ai_whatsapp_address_set,
            'delivery_method': order.carrier_id.name or False,
            'needs_delivery_address': order._om_ai_whatsapp_needs_shipping(),
        }

    def _wa_send_document(self, report_ref, record, text):
        """ Send the PDF of ``record`` with ``text`` to the customer. """
        conversation = self._wa()
        report = self.env.ref(report_ref).sudo()
        pdf, _type = report._render_qweb_pdf(report_ref, record.ids)
        name = '%s.pdf' % re.sub(r'[^\w.-]+', '_', record.name or 'document')
        attachment = self.env['ir.attachment'].sudo().create({
            'name': name, 'raw': pdf, 'mimetype': 'application/pdf',
            'res_model': 'discuss.channel', 'res_id': conversation.channel_id.id,
        })
        account = conversation.account_id
        if account.can_send_files:
            conversation._om_ai_send(text, attachments=attachment)
        else:
            conversation._om_ai_send(text)
        return attachment

    def _wa_payment_link(self, record):
        wizard = self.env['payment.link.wizard'].sudo().with_context(
            active_model=record._name, active_id=record.id).create({})
        return wizard.link

    def _wa_scope_search(self, model, domain, level=None, limit=5, order=None):
        conversation = self._wa()
        full = Domain.AND([conversation._om_ai_scope_domain(level), domain])
        return self.env[model].search(full, limit=limit, order=order)

    # ------------------------------------------------------------
    # Level 0: anyone
    # ------------------------------------------------------------
    def _ai_tool_wa_search_products(self, tool, query='', limit=5):
        conversation = self._wa()
        level = conversation._om_ai_level()
        partner = conversation._om_ai_customer()
        limit = max(1, min(int(limit or 5), MAX_PRODUCTS))
        products = self.env['product.product'].search(self._wa_product_domain(query), limit=limit)
        if not products and query:
            # each word alone, for a customer who wrote more than the name
            domain = Domain.OR([self._wa_product_domain(word) for word in query.split()])
            products = self.env['product.product'].search(domain, limit=limit)
        return {'products': [self._wa_product_info(product, partner, level) for product in products],
                'note': 'Prices are for one unit, without and with taxes.'}

    def _ai_tool_wa_product_details(self, tool, product_id):
        conversation = self._wa()
        product = self._wa_product(product_id)
        info = self._wa_product_info(product, conversation._om_ai_customer(), conversation._om_ai_level())
        info['description'] = product.description_sale or False
        variants = product.product_tmpl_id.product_variant_ids - product
        if variants:
            info['other_variants'] = [{'id': variant.id, 'name': variant.display_name} for variant in variants[:20]]
        return info

    def _ai_tool_wa_set_customer_name(self, tool, name, language=None):
        """ Make the contact of a new customer, with the WhatsApp number. """
        conversation = self._wa()
        name = (name or '').strip()
        if len(name) < 2:
            raise UserError(self.env._('Give the full name the customer chose.'))
        partner = conversation._om_ai_customer()
        if partner:
            if conversation.partner_created and partner.name != name:
                partner.sudo().name = name
                return {'done': True, 'customer_name': name}
            return {'done': False, 'customer_name': partner.name,
                    'note': 'The customer is already known; their name in Odoo is kept.'}
        if len(conversation._om_ai_number_partners()) > 1:
            raise UserError(self.env._('This number is on several contacts: a person must help (wa_hand_over).'))
        values = {
            'name': name,
            'phone': conversation.number,
            'company_id': False,
            'category_id': [fields.Command.link(self.env.ref('om_ai_whatsapp.partner_category_whatsapp').id)],
            'customer_rank': 1,
        }
        langs = dict(self.env['res.lang'].get_installed())
        if language:
            code = next((code for code in langs if code.lower().replace('-', '_').startswith(
                language.lower().replace('-', '_'))), None)
            if code:
                values['lang'] = code
        partner = self.env['res.partner'].sudo().with_context(om_whatsapp_channel_id=conversation.channel_id.id) \
            .create(values)
        partner.message_post(body=self.env._('Contact made by the WhatsApp Assistant from %s.', conversation.number))
        conversation.write({'partner_id': partner.id, 'partner_created': True})
        if conversation.channel_id.om_whatsapp_partner_id != partner:
            conversation.channel_id._om_whatsapp_link_partner(partner)
        return {'done': True, 'customer_name': partner.name, 'level': 1}

    def _ai_tool_wa_add_to_cart(self, tool, product_id, quantity=1):
        conversation = self._wa()
        partner = conversation._om_ai_customer()
        if not partner:
            if len(conversation._om_ai_number_partners()) > 1:
                raise UserError(self.env._('This number is on several contacts: a person must take the order '
                                           '(wa_hand_over).'))
            return {
                'added': False,
                'need_customer_name': True,
                'whatsapp_profile_name': conversation.profile_name or False,
                'instruction': 'Before the first item, ask for the name of the order. If there is a WhatsApp '
                               'profile name, offer it ("Shall I put the order under <name>?"). Then call '
                               'wa_set_customer_name and add the item again.',
            }
        product = self._wa_product(product_id)
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise UserError(self.env._('The quantity must be a number.')) from None
        if quantity <= 0:
            raise UserError(self.env._('The quantity must be more than 0; use wa_set_cart_quantity to remove.'))
        order = self._wa_order()
        line = order.order_line.filtered(lambda l: l.product_id == product and not getattr(l, 'is_delivery', False))[:1]
        wanted = quantity + (line.product_uom_qty if line else 0.0)
        tracked, free = self._wa_stock(product)
        if tracked and wanted > free:
            available = max(max(free, 0.0) - (line.product_uom_qty if line else 0.0), 0.0)
            return {
                'added': False,
                'available_quantity': available,
                'in_cart': line.product_uom_qty if line else 0.0,
                'instruction': 'Not enough in stock. Tell the customer how many are available and ask whether to '
                               'add that many instead.' if available else
                               'Out of stock: tell the customer and suggest a similar product.',
            }
        self._wa_reopen(order)
        if line:
            line.product_uom_qty = wanted
        else:
            self.env['sale.order.line'].create({'order_id': order.id, 'product_id': product.id,
                                                'product_uom_qty': quantity})
        return {'added': True, 'cart': self._wa_cart(order)}

    def _ai_tool_wa_hand_over(self, tool, reason='', message_to_customer=''):
        conversation = self._wa()
        conversation._om_ai_hand_over(
            reason or self.env._('the assistant asked for a person'),
            message=message_to_customer or self.env._("A colleague will answer you here shortly."))
        return {'done': True, 'note': 'A person answers from now on; the customer was told.'}

    # ------------------------------------------------------------
    # Level 1: the number is one known contact
    # ------------------------------------------------------------
    def _ai_tool_wa_view_cart(self, tool):
        return self._wa_cart(self._wa_order(create=False))

    def _ai_tool_wa_set_cart_quantity(self, tool, product_id, quantity):
        order = self._wa_order(create=False)
        line = order.order_line.filtered(
            lambda l: l.product_id.id == int(product_id) and not getattr(l, 'is_delivery', False))[:1]
        if not line:
            raise UserError(self.env._('This product is not in the quotation.'))
        quantity = float(quantity)
        if quantity > line.product_uom_qty:
            tracked, free = self._wa_stock(line.product_id)
            if tracked and quantity > free:
                return {'done': False, 'available_quantity': max(free, 0.0),
                        'instruction': 'Not enough in stock: tell the customer and ask.'}
        self._wa_reopen(order)
        if quantity <= 0:
            line.unlink()
        else:
            line.product_uom_qty = quantity
        return {'done': True, 'cart': self._wa_cart(order)}

    def _ai_tool_wa_set_delivery_address(self, tool, street, city, zip_code='', country='', state='', street2='',
                                         latitude=None, longitude=None):
        """ The delivery address the customer gave. On a contact made here
        and without an address, it becomes their address; else a delivery
        address of the contact. Saved addresses are never shown below
        level 2. """
        conversation = self._wa()
        partner = self._wa_customer().sudo()
        order = self._wa_order(create=False)
        if not (street or '').strip() or not (city or '').strip():
            raise UserError(self.env._('Give at least the street and the city.'))
        company = conversation.account_id.company_id
        Country = self.env['res.country'].sudo()
        country_rec = Country
        if country:
            name = country.strip()
            country_rec = Country.search(['|', ('code', '=ilike', name), ('name', '=ilike', name)], limit=1)
        country_rec = country_rec or company.country_id
        state_rec = self.env['res.country.state']
        if state and country_rec:
            state_rec = self.env['res.country.state'].sudo().search([
                ('country_id', '=', country_rec.id), '|', ('code', '=ilike', state.strip()),
                ('name', '=ilike', state.strip())], limit=1)
        values = {
            'street': street.strip(), 'street2': (street2 or '').strip() or False, 'city': city.strip(),
            'zip': (zip_code or '').strip() or False, 'country_id': country_rec.id or False,
            'state_id': state_rec.id or False,
        }
        if latitude and longitude:
            values.update(partner_latitude=float(latitude), partner_longitude=float(longitude))
        if conversation.partner_created and not partner.street and not partner.city:
            partner.write(values)
            shipping = partner
        else:
            shipping = self.env['res.partner'].sudo().create(dict(
                values, parent_id=partner.id, type='delivery', name=partner.name))
        self._wa_reopen(order)
        order.sudo().write({'partner_shipping_id': shipping.id, 'om_ai_whatsapp_address_set': True})
        if order.carrier_id:
            order.sudo()._remove_delivery_line()
        return {'done': True, 'delivery_address': shipping._display_address(without_name=True),
                'instruction': 'Read the address back to the customer so they can correct it.'}

    def _ai_tool_wa_use_saved_address(self, tool):
        conversation = self._wa()
        partner = self._wa_customer().sudo()
        order = self._wa_order(create=False)
        shipping = self.env['res.partner'].sudo().browse(partner.address_get(['delivery'])['delivery'])
        if not shipping.street and not shipping.city:
            return {'done': False, 'note': 'There is no saved address: ask for the delivery address.'}
        self._wa_reopen(order)
        order.sudo().write({'partner_shipping_id': shipping.id, 'om_ai_whatsapp_address_set': True})
        result = {'done': True}
        if conversation._om_ai_level() >= 2:
            result['delivery_address'] = shipping._display_address(without_name=True)
        else:
            result['note'] = 'The saved address is used. It is not shown, as the customer is not verified.'
        return result

    def _ai_tool_wa_set_email(self, tool, email):
        conversation = self._wa()
        partner = self._wa_customer().sudo()
        email = (email or '').strip()
        if not EMAIL_RE.match(email):
            raise UserError(self.env._('This is not a valid email address.'))
        if not conversation.partner_created:
            return {'done': False, 'note': 'The email of a known contact is never changed on WhatsApp: a person can '
                                           'change it.'}
        partner.email = email
        return {'done': True}

    def _ai_tool_wa_delivery_options(self, tool):
        conversation = self._wa()
        order = self._wa_order(create=False).sudo()
        if not order._om_ai_whatsapp_needs_shipping():
            return {'options': [], 'note': 'Nothing to deliver in this quotation.'}
        if not order.om_ai_whatsapp_address_set:
            return {'options': [], 'note': 'Ask for the delivery address first.'}
        options = []
        for carrier in conversation.account_id.om_ai_carrier_ids.sudo():
            if not carrier._is_available_for_order(order):
                continue
            rate = carrier.rate_shipment(order)
            if not rate.get('success'):
                continue
            options.append({'id': carrier.id, 'name': carrier.name,
                            'price': rate['price'], 'currency': order.currency_id.name,
                            'note': rate.get('warning_message') or False})
        return {'options': options} if options else {
            'options': [], 'note': 'No delivery method reaches this address: offer a colleague (wa_hand_over).'}

    def _ai_tool_wa_set_delivery_method(self, tool, carrier_id):
        conversation = self._wa()
        order = self._wa_order(create=False).sudo()
        carrier = conversation.account_id.om_ai_carrier_ids.sudo().filtered(lambda c: c.id == int(carrier_id))
        if not carrier or not order.om_ai_whatsapp_address_set or not carrier._is_available_for_order(order):
            raise UserError(self.env._('This delivery method is not offered for this address: use '
                                       'wa_delivery_options.'))
        rate = carrier.rate_shipment(order)
        if not rate.get('success'):
            raise UserError(rate.get('error_message') or self.env._('No price for this delivery.'))
        self._wa_reopen(order)
        order.set_delivery_line(carrier, rate['price'])
        return {'done': True, 'cart': self._wa_cart(order.with_env(self.env))}

    def _ai_check_wa_send_quotation(self):
        error = self._wa_order(create=False)._om_ai_whatsapp_ready_error()
        if error:
            raise UserError(error)

    def _ai_tool_wa_send_quotation(self, tool):
        """ Runs once the customer said YES: the quotation PDF and the online
        payment link. The order confirms when it is paid. """
        conversation = self._wa()
        order = self._wa_order(create=False)
        error = order._om_ai_whatsapp_ready_error()
        if error:
            raise UserError(error)
        order.sudo().write({'prepayment_percent': 1.0, 'require_signature': False})
        if order.state == 'draft':
            order.action_quotation_sent()
        link = self._wa_payment_link(order)
        text = self.env._(
            "Here is your quotation %(order)s for %(amount)s.\nPay online to confirm your order:\n%(link)s",
            order=order.name, amount=order._om_ai_whatsapp_amount(order.amount_total), link=link)
        self._wa_send_document('sale.action_report_saleorder', order, text)
        order.sudo().write({'om_ai_whatsapp_link_date': fields.Datetime.now(), 'om_ai_whatsapp_reminded': False})
        order.message_post(body=self.env._('The customer confirmed the quotation on WhatsApp; the quotation and '
                                           'the payment link were sent.'), subtype_xmlid='mail.mt_note')
        conversation.order_id = False
        return {'done': True, 'sent': 'quotation PDF and payment link', 'quotation': order.name}

    def _ai_tool_wa_list_orders(self, tool):
        orders = self._wa_scope_search('sale.order', [], limit=5, order='date_order desc, id desc')
        return {'orders': [order._om_ai_whatsapp_status() for order in orders]}

    def _wa_find_order(self, reference):
        reference = (reference or '').strip()
        if not reference:
            raise UserError(self.env._('Give the order reference.'))
        order = self._wa_scope_search('sale.order', [('name', '=ilike', reference)], limit=1)
        if not order:
            order = self._wa_scope_search('sale.order', [('name', 'ilike', reference)], limit=2)
            if len(order) != 1:
                raise UserError(self.env._('No order %s for this customer.', reference))
        return order

    def _ai_tool_wa_order_status(self, tool, reference):
        order = self._wa_find_order(reference)
        status = order._om_ai_whatsapp_status(details=True)
        return status

    def _ai_tool_wa_order_payment_link(self, tool, reference):
        conversation = self._wa()
        order = self._wa_find_order(reference)
        if not order._has_to_be_paid():
            return {'sent': False, 'note': 'This order has nothing left to pay online.'}
        link = self._wa_payment_link(order)
        conversation._om_ai_send(self.env._("Pay %(order)s (%(amount)s) online here:\n%(link)s", order=order.name,
                                            amount=order._om_ai_whatsapp_amount(order.amount_total - order.amount_paid),
                                            link=link))
        if not order.om_ai_whatsapp_link_date:
            order.sudo().om_ai_whatsapp_link_date = fields.Datetime.now()
        return {'sent': True, 'note': 'The link was sent in its own message: do not repeat it.'}

    def _ai_tool_wa_send_verification_code(self, tool):
        conversation = self._wa()
        if not conversation.account_id.om_ai_email_code or conversation._om_ai_level() >= 2:
            return {'sent': False, 'note': 'No code is needed: the customer may see their invoices and balance.'}
        masked = self._wa()._om_ai_send_code()
        return {'sent': True, 'email': masked,
                'instruction': 'Tell the customer a 6-digit code was mailed to %s and to type it here. Never ask '
                               'for the code in another way.' % masked}

    # ------------------------------------------------------------
    # Level 2: verified by the email code
    # ------------------------------------------------------------
    def _wa_invoice_domain(self):
        return [('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted')]

    def _ai_tool_wa_list_invoices(self, tool, unpaid_only=False):
        domain = self._wa_invoice_domain()
        if unpaid_only:
            domain = [*domain, ('payment_state', 'in', ('not_paid', 'partial'))]
        invoices = self._wa_scope_search('account.move', domain, limit=10,
                                         order='invoice_date desc, id desc')
        return {'invoices': [{
            'reference': move.name,
            'type': 'credit note' if move.move_type == 'out_refund' else 'invoice',
            'date': fields.Date.to_string(move.invoice_date),
            'due_date': fields.Date.to_string(move.invoice_date_due),
            'total': move.amount_total,
            'amount_due': move.amount_residual,
            'currency': move.currency_id.name,
            'payment_status': dict(move._fields['payment_state']._description_selection(self.env)).get(
                move.payment_state),
        } for move in invoices]}

    def _ai_tool_wa_send_invoice(self, tool, reference):
        reference = (reference or '').strip()
        invoice = self._wa_scope_search('account.move', [*self._wa_invoice_domain(), ('name', '=ilike', reference)],
                                        limit=1)
        if not invoice:
            raise UserError(self.env._('No invoice %s for this customer.', reference))
        lines = [self.env._("Your invoice %(invoice)s of %(amount)s.", invoice=invoice.name,
                            amount=invoice._om_ai_whatsapp_amount(invoice.amount_total))]
        if invoice.move_type == 'out_invoice' and invoice.amount_residual > 0:
            lines.append(self.env._("Amount due: %(amount)s. Pay online here:\n%(link)s",
                                    amount=invoice._om_ai_whatsapp_amount(invoice.amount_residual),
                                    link=self._wa_payment_link(invoice)))
        self._wa_send_document('account.account_invoices', invoice, '\n'.join(lines))
        return {'sent': True, 'note': 'The PDF and the payment link were sent: do not repeat the link.'}

    def _ai_tool_wa_open_balance(self, tool):
        invoices = self._wa_scope_search(
            'account.move', [*self._wa_invoice_domain(), ('payment_state', 'in', ('not_paid', 'partial'))],
            limit=None)
        company = self._wa_company()
        total = sum(invoices.mapped('amount_residual_signed'))
        overdue = sum(invoices.filtered(
            lambda m: m.invoice_date_due and m.invoice_date_due < fields.Date.context_today(self)
        ).mapped('amount_residual_signed'))
        return {'open_balance': company.currency_id.round(total), 'overdue': company.currency_id.round(overdue),
                'currency': company.currency_id.name, 'open_invoices': len(invoices)}

    def _ai_tool_wa_my_addresses(self, tool):
        partner = self._wa_customer().sudo()
        addresses = partner | partner.child_ids.filtered(lambda p: p.type in ('delivery', 'invoice'))
        return {'addresses': [{
            'type': address.type if address != partner else 'main',
            'address': address._display_address(without_name=True),
        } for address in addresses if address.street or address.city]}
