from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools import queries


class OmShopifyCompany(models.Model):
    """ A B2B company of Shopify (Shopify Plus), linked to an Odoo company contact. """
    _name = 'om.shopify.company'
    _description = 'Shopify B2B Company'
    _inherit = ['om.connector.binding.mixin']
    _order = 'store_id, name'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'partner_id'

    name = fields.Char(readonly=True)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    partner_id = fields.Many2one('res.partner', string='Company Contact', required=True, ondelete='cascade',
                                 index=True)
    location_ids = fields.One2many('om.shopify.company.location', 'company_binding_id', string='Locations')

    _store_external_unique = models.Constraint('unique (store_id, external_id)',
                                               "A Shopify company is linked once per store.")

    @api.model
    def _connector_job_shopify_import_company(self, job):
        return self._shopify_import_company(job.backend, job.payload['id'])

    @api.model
    def _connector_job_shopify_company_webhook(self, job):
        payload = job.payload
        gid = payload.get('admin_graphql_api_id') or (payload.get('company') or {}).get('admin_graphql_api_id')
        if not gid or '/Company/' not in gid:
            return _("No company in this webhook")
        return self._shopify_import_company(job.backend, gid)

    @api.model
    def _shopify_import_company(self, store, gid):
        """ Create or update the company contact of the Shopify company ``gid``, its locations as
        addresses (with their payment terms and tax exemption), and its contacts as its people. """
        data = store._shopify_execute(queries.COMPANY, {'id': gid}).get('company')
        if not data:
            return _("Company %(id)s does not exist anymore", id=gid)
        Partner = self.env['res.partner']
        binding = self._connector_find(store, gid)
        partner = binding.partner_id
        vals = {'name': data['name'], 'ref': data.get('externalId') or False}
        if partner:
            partner.write(vals)
        else:
            partner = Partner.create(vals)
        binding = self._connector_bind(store, gid, partner, {'name': data['name']})
        Location = self.env['om.shopify.company.location']
        for location in (data.get('locations') or {}).get('nodes') or []:
            Location._shopify_import(store, binding, location)
        Customer = self.env['om.shopify.customer']
        for contact in (data.get('contacts') or {}).get('nodes') or []:
            person = Customer._connector_find(store, (contact.get('customer') or {}).get('id') or '').partner_id
            if person and not person.parent_id and person != partner:
                person.parent_id = partner
        return partner


class OmShopifyCompanyLocation(models.Model):
    """ A location of a Shopify B2B company: its addresses, payment terms and tax exemption. """
    _name = 'om.shopify.company.location'
    _description = 'Shopify B2B Company Location'
    _inherit = ['om.connector.binding.mixin']
    _order = 'company_binding_id, name'
    _connector_backend_field = 'store_id'
    _connector_record_field = 'partner_id'

    name = fields.Char(readonly=True)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    company_binding_id = fields.Many2one('om.shopify.company', string='Shopify Company', required=True,
                                         ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', string='Delivery Address', required=True, ondelete='cascade')
    invoice_partner_id = fields.Many2one('res.partner', string='Invoice Address', ondelete='set null')
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Terms', ondelete='set null')
    tax_exempt = fields.Boolean(readonly=True)

    _store_external_unique = models.Constraint('unique (store_id, external_id)',
                                               "A Shopify company location is linked once per store.")

    @api.model
    def _shopify_address_vals(self, address):
        if not address:
            return {}
        country = self.env['res.country'].search([('code', '=', address.get('countryCode'))], limit=1) \
            if address.get('countryCode') else self.env['res.country']
        state = self.env['res.country.state']
        if country and address.get('zoneCode'):
            state = state.search([('country_id', '=', country.id), ('code', '=', address['zoneCode'])], limit=1)
        return {
            'street': address.get('address1') or False, 'street2': address.get('address2') or False,
            'city': address.get('city') or False, 'zip': address.get('zip') or False,
            'country_id': country.id, 'state_id': state.id, 'phone': address.get('phone') or False,
        }

    @api.model
    def _shopify_payment_term(self, template):
        """ The Odoo payment terms of a Shopify payment terms template, found by name or created. """
        if not template or not template.get('name'):
            return self.env['account.payment.term']
        Term = self.env['account.payment.term']
        term = Term.search([('name', '=ilike', template['name'])], limit=1)
        if not term and template.get('dueInDays') is not None:
            term = Term.create({'name': template['name'], 'line_ids': [fields.Command.create({
                'value': 'percent', 'value_amount': 100.0, 'nb_days': int(template['dueInDays'])})]})
        return term

    @api.model
    def _shopify_import(self, store, company_binding, data):
        company = company_binding.partner_id
        binding = self._connector_find(store, data['id'])
        fiscal_position = store.b2b_tax_exempt_fiscal_position_id if (data.get('taxSettings') or {}).get('taxExempt') \
            else self.env['account.fiscal.position']
        term = self._shopify_payment_term(
            ((data.get('buyerExperienceConfiguration') or {}).get('paymentTermsTemplate')) or {})
        delivery_vals = {'name': data.get('name') or company.name, 'type': 'delivery', 'parent_id': company.id,
                         **self._shopify_address_vals(data.get('shippingAddress'))}
        invoice_vals = {'name': data.get('name') or company.name, 'type': 'invoice', 'parent_id': company.id,
                        **self._shopify_address_vals(data.get('billingAddress') or data.get('shippingAddress'))}
        Partner = self.env['res.partner']
        delivery = binding.partner_id
        if delivery:
            delivery.write(delivery_vals)
        else:
            delivery = Partner.create(delivery_vals)
        invoice = binding.invoice_partner_id
        if invoice:
            invoice.write(invoice_vals)
        else:
            invoice = Partner.create(invoice_vals)
        for partner in company | delivery | invoice:
            if fiscal_position:
                partner.with_company(store.company_id).property_account_position_id = fiscal_position
        if term:
            company.with_company(store.company_id).property_payment_term_id = term
        return self._connector_bind(store, data['id'], delivery, {
            'name': data.get('name'), 'company_binding_id': company_binding.id, 'invoice_partner_id': invoice.id,
            'payment_term_id': term.id, 'tax_exempt': bool((data.get('taxSettings') or {}).get('taxExempt')),
        })


class OmShopifyPriceList(models.Model):
    """ A price list of Shopify (a market or a B2B catalog), and the Odoo pricelist that fills it. """
    _name = 'om.shopify.price.list'
    _description = 'Shopify Price List'
    _order = 'store_id, name'
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True)
    store_id = fields.Many2one('om.shopify.store', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='store_id.company_id', store=True)
    shopify_gid = fields.Char(string='Shopify ID', required=True, readonly=True)
    currency_code = fields.Char(string='Currency', readonly=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Odoo Pricelist', check_company=True,
                                   help="Its prices are sent as the fixed prices of this Shopify price list.")

    _store_gid_unique = models.Constraint('unique (store_id, shopify_gid)', "A price list is imported once per store.")

    @api.model
    def _shopify_import(self, store):
        existing = {p.shopify_gid: p for p in self.search([('store_id', '=', store.id)])}
        for node in store._shopify_paginate(queries.PRICE_LISTS, {}, 'priceLists'):
            vals = {'name': node['name'], 'currency_code': node.get('currency')}
            if node['id'] in existing:
                existing[node['id']].write(vals)
            else:
                existing[node['id']] = self.create({'store_id': store.id, 'shopify_gid': node['id'], **vals})
        return self.browse([p.id for p in existing.values()])

    def _shopify_export(self, batch=250):
        """ Send the prices of the linked variants, computed by the Odoo pricelist, as fixed prices. """
        self.ensure_one()
        if not self.pricelist_id:
            return 0
        if self.currency_code and self.pricelist_id.currency_id.name != self.currency_code:
            raise UserError(_("%(pricelist)s is in %(odoo)s, the Shopify price list %(shopify)s in %(currency)s.",
                              pricelist=self.pricelist_id.display_name, odoo=self.pricelist_id.currency_id.name,
                              shopify=self.name, currency=self.currency_code))
        variants = self.env['om.shopify.product'].search([('store_id', '=', self.store_id.id), ('active', '=', True)])
        currency = self.pricelist_id.currency_id.name
        prices = [{'variantId': v.external_id,
                   'price': {'amount': f'{self.pricelist_id._get_product_price(v.product_id, 1.0):.2f}',
                             'currencyCode': currency}}
                  for v in variants]
        for start in range(0, len(prices), batch):
            self.store_id._shopify_mutate(queries.PRICE_LIST_FIXED_PRICES_ADD,
                                          {'priceListId': self.shopify_gid, 'prices': prices[start:start + batch]},
                                          'priceListFixedPricesAdd')
        return len(prices)


class OmShopifyStoreB2B(models.Model):
    _inherit = 'om.shopify.store'

    b2b_import = fields.Boolean(string='Import B2B Companies',
                                help="Imports the B2B companies of Shopify Plus, with their locations, payment terms "
                                     "and tax exemption, and links their orders to them.")
    b2b_tax_exempt_fiscal_position_id = fields.Many2one(
        'account.fiscal.position', string='Fiscal Position of Tax-Exempt Locations', check_company=True)
    company_binding_ids = fields.One2many('om.shopify.company', 'store_id', string='B2B Companies')
    price_list_ids = fields.One2many('om.shopify.price.list', 'store_id', string='Price Lists')

    def _shopify_webhook_handlers(self):
        handlers = super()._shopify_webhook_handlers()
        if self.b2b_import:
            company = ('om.shopify.company', '_connector_job_shopify_company_webhook')
            handlers.update({'COMPANIES_CREATE': company, 'COMPANIES_UPDATE': company})
        return handlers

    def action_shopify_import_companies(self):
        self._shopify_ensure_connected()
        for store in self:
            store._connector_enqueue_once('_connector_job_shopify_fetch_companies', name=_("Import the B2B companies"))
        return self._shopify_notification(_("The companies are being imported: follow it in Jobs."), kind='info')

    def action_shopify_import_price_lists(self):
        self._shopify_ensure_connected()
        for store in self:
            self.env['om.shopify.price.list']._shopify_import(store)
        return self._shopify_notification(_("Price lists imported: give them an Odoo pricelist."))

    @api.model
    def _connector_job_shopify_fetch_companies(self, job):
        store = job.backend
        count = 0
        for node in store._shopify_paginate(queries.COMPANY_IDS, {}, 'companies'):
            store._connector_enqueue('_connector_job_shopify_import_company', {'id': node['id'],
                                     'updatedAt': node.get('updatedAt')}, model_name='om.shopify.company',
                                     name=_("Company %(id)s", id=node['id'].rsplit('/', 1)[-1]),
                                     dedupe_key=f"company:{node['id']}", priority=25)
            count += 1
        return _("%(count)s company(ies) to import", count=count)

    @api.model
    def _connector_job_shopify_export_prices(self, job):
        result = super()._connector_job_shopify_export_prices(job)
        sent = sum(price_list._shopify_export() for price_list in job.backend.price_list_ids.filtered('pricelist_id'))
        return _("%(result)s; %(count)s price list price(s) sent", result=result, count=sent) if sent else result
