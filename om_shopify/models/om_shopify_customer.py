from odoo import _, api, fields, models

from ..tools import queries


class OmShopifyCustomer(models.Model):
    """ A Shopify customer, linked to an Odoo contact. """
    _name = 'om.shopify.customer'
    _description = 'Shopify Customer'
    _inherit = ['om.connector.binding.mixin']
    _order = 'store_id, id desc'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'partner_id'

    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True, ondelete='cascade', index=True)

    _store_external_unique = models.Constraint('unique (store_id, external_id)',
                                               "A Shopify customer is linked once per store.")

    @api.model
    def _connector_job_shopify_import_customer(self, job):
        return self._shopify_import_customer(job.backend, job.payload['id'])

    @api.model
    def _connector_job_shopify_customer_webhook(self, job):
        gid = job.payload.get('admin_graphql_api_id') or f"gid://shopify/Customer/{job.payload['id']}"
        return self._shopify_import_customer(job.backend, gid)

    @api.model
    def _shopify_import_customer(self, store, gid):
        """ Create or update the contact of the Shopify customer ``gid``. Gives the contact. """
        customer = store._shopify_execute(store._shopify_query(queries.CUSTOMER), {'id': gid}).get('customer')
        if not customer:
            return _("Customer %(id)s does not exist anymore", id=gid)
        address = customer.get('defaultAddress') or {}
        email = (customer.get('defaultEmailAddress') or {}).get('emailAddress')
        binding = self._connector_find(store, gid)
        partner = binding.partner_id
        if partner:
            # an existing contact gets the blanks filled, never its data replaced
            name = ' '.join(filter(None, [customer.get('firstName'), customer.get('lastName')]))
            vals = {'name': name, 'email': email,
                    'phone': (customer.get('defaultPhoneNumber') or {}).get('phoneNumber'),
                    **self._shopify_address_vals(address)}
            partner.write({k: v for k, v in vals.items() if v and not partner[k]})
        else:
            partner, _invoice, _delivery = self._shopify_partner(store, {
                'customer': customer, 'email': email, 'billingAddress': address, 'name': gid,
            })
        if tags := [t for t in customer.get('tags') or [] if t]:
            Category = self.env['res.partner.category']
            partner.category_id = [fields.Command.link(
                (Category.search([('name', '=', tag)], limit=1) or Category.create({'name': tag})).id) for tag in tags]
        store._shopify_apply_metafields('customer', partner, customer.get('metafields'))
        return partner

    @api.model
    def _shopify_partner(self, store, order):
        """ The contact, invoice address and delivery address of a Shopify order:
        ``(partner, invoice, delivery)``. """
        customer = order.get('customer') or {}
        billing = order.get('billingAddress') or {}
        shipping = order.get('shippingAddress') or {}
        email = (order.get('email') or ((customer.get('defaultEmailAddress') or {}).get('emailAddress')) or '').strip()
        phone = order.get('phone') or (customer.get('defaultPhoneNumber') or {}).get('phoneNumber') or False

        partner = None
        if customer.get('id'):
            partner = self._connector_find(store, customer['id']).partner_id
        if not partner and email:
            partner = self.env['res.partner'].search([
                ('email', '=ilike', email), ('parent_id', '=', False),
                ('company_id', 'in', [False, store.company_id.id]),
            ], limit=1)
        if not partner:
            name = ' '.join(filter(None, [customer.get('firstName'), customer.get('lastName')])) \
                or billing.get('name') or shipping.get('name') or email or order.get('name')
            vals = {'name': name, 'email': email or False, 'phone': phone,
                    **self._shopify_address_vals(billing or shipping)}
            partner = self.env['res.partner'].create(vals)
        if customer.get('id'):
            self._connector_bind(store, customer['id'], partner)
        invoice = self._shopify_child(partner, 'invoice', billing) if billing else partner
        delivery = self._shopify_child(partner, 'delivery', shipping) if shipping else invoice
        return partner, invoice, delivery

    @api.model
    def _shopify_address_vals(self, address):
        if not address:
            return {}
        country = self.env['res.country'].search([('code', '=', address.get('countryCodeV2'))], limit=1) \
            if address.get('countryCodeV2') else self.env['res.country']
        state = self.env['res.country.state']
        if country and address.get('provinceCode'):
            state = state.search([('country_id', '=', country.id), ('code', '=', address['provinceCode'])], limit=1)
        return {
            'street': address.get('address1') or False,
            'street2': address.get('address2') or False,
            'city': address.get('city') or False,
            'zip': address.get('zip') or False,
            'country_id': country.id,
            'state_id': state.id,
        }

    @api.model
    def _shopify_child(self, partner, address_type, address):
        """ The address of ``partner``: itself when it is the same, else one of its own addresses of
        this type, found or created. Never the address of another contact. """
        vals = self._shopify_address_vals(address)
        name = address.get('name') or partner.name

        def same(record):
            return all((record[key].id if hasattr(record[key], 'id') else record[key] or False) == value
                       for key, value in vals.items())

        if same(partner) and name == partner.name:
            return partner
        child = partner.child_ids.filtered(lambda c: c.type == address_type and c.name == name and same(c))[:1]
        if child:
            return child
        return self.env['res.partner'].create({
            'parent_id': partner.id,
            'type': address_type,
            'name': name,
            'phone': address.get('phone') or False,
            **vals,
        })
