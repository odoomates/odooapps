from odoo import _, api, fields, models


class OmWoocommerceCustomer(models.Model):
    """ A WooCommerce customer (a registered account), linked to an Odoo contact. """
    _name = 'om.woocommerce.customer'
    _description = 'WooCommerce Customer'
    _inherit = ['om.connector.binding.mixin']
    _order = 'store_id, id desc'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'partner_id'

    store_id = fields.Many2one('om.woocommerce.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True, ondelete='cascade', index=True)

    _sql_constraints = [
        ('store_external_unique', 'unique (store_id, external_id)',
         "A WooCommerce customer is linked once per store."),
    ]

    @api.model
    def _connector_job_woo_import_customer(self, job):
        return self._woo_import_customer(job.backend, job.payload['id'], data=job.payload.get('data'))

    @api.model
    def _connector_job_woo_customer_webhook(self, job):
        return self._woo_import_customer(job.backend, job.payload['id'])

    @api.model
    def _woo_import_customer(self, store, woo_id, data=None):
        """ Create or update the contact of the WooCommerce customer ``woo_id``. Gives the contact. """
        customer = data or store._woo_get(f'customers/{woo_id}')
        if not customer:
            return _("Customer %(id)s does not exist anymore", id=woo_id)
        billing = self._woo_address(customer.get('billing'))
        name = self._woo_name(customer.get('first_name'), customer.get('last_name')) or billing.get('name') \
            or customer.get('username')
        email = customer.get('email') or billing.get('email')
        partner = self._connector_find(store, woo_id).partner_id
        if partner:
            # an existing contact gets the blanks filled, never its data replaced
            partner._connector_fill_blanks({
                'name': name, 'email': email, 'phone': billing.get('phone'),
                **self.env['res.partner']._connector_address_vals(billing),
            })
        else:
            partner = self.env['res.partner']._connector_find_or_create(store.company_id, email, name, billing)
            self._connector_bind(store, woo_id, partner)
        if billing.get('company') and not partner.company_name and not partner.parent_id:
            partner.company_name = billing['company']
        store._woo_apply_meta('customer', partner, customer.get('meta_data'))
        return partner

    @api.model
    def _woo_name(self, first_name, last_name):
        return ' '.join(filter(None, [(first_name or '').strip(), (last_name or '').strip()]))

    @api.model
    def _woo_address(self, address):
        """ A WooCommerce address (billing, shipping) in the format of ``om_connector_base``; empty when
        it has no street, city nor name. """
        address = address or {}
        name = self._woo_name(address.get('first_name'), address.get('last_name')) or address.get('company')
        if not any(address.get(key) for key in ('address_1', 'city', 'postcode')) and not name:
            return {}
        return {
            'name': name,
            'company': address.get('company') or False,
            'street': address.get('address_1'),
            'street2': address.get('address_2'),
            'city': address.get('city'),
            'zip': address.get('postcode'),
            'state_code': address.get('state'),
            'country_code': address.get('country'),
            'phone': address.get('phone'),
            'email': address.get('email'),
        }

    @api.model
    def _woo_partner(self, store, order):
        """ The contact, invoice address and delivery address of a WooCommerce order:
        ``(partner, invoice, delivery)``. Guests (no customer) are found by email. """
        billing = self._woo_address(order.get('billing'))
        shipping = self._woo_address(order.get('shipping'))
        if shipping and not any(shipping.get(key) for key in ('street', 'city', 'zip')):
            shipping = {}
        email = (billing.get('email') or '').strip()
        customer_id = order.get('customer_id') or 0
        partner = self._connector_find(store, customer_id).partner_id if customer_id else None
        if not partner:
            name = billing.get('name') or shipping.get('name') or email or _("WooCommerce order %(number)s",
                                                                           number=order.get('number'))
            partner = self.env['res.partner']._connector_find_or_create(
                store.company_id, email, name, billing or shipping, billing.get('phone'))
            if billing.get('company') and not partner.company_name and not partner.parent_id:
                partner.company_name = billing['company']
            if customer_id:
                self._connector_bind(store, customer_id, partner)
        invoice = partner._connector_address('invoice', billing) if billing else partner
        delivery = partner._connector_address('delivery', shipping) if shipping else invoice
        return partner, invoice, delivery
