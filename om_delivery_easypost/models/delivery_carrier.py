import json
import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

EASYPOST_API_URL = 'https://api.easypost.com/v2'
EASYPOST_TIMEOUT = 45
EASYPOST_CREDENTIAL_GROUPS = 'base.group_system,stock.group_stock_manager'
EASYPOST_LABEL_EXTENSIONS = {'PDF': 'pdf', 'ZPL': 'zpl', 'PNG': 'png'}


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('easypost', 'EasyPost')],
        ondelete={'easypost': 'set default'},
    )
    easypost_test_api_key = fields.Char(
        string='EasyPost Test API Key', groups=EASYPOST_CREDENTIAL_GROUPS, copy=False,
        help='Test API key from the EasyPost dashboard, used in the test environment.',
    )
    easypost_production_api_key = fields.Char(
        string='EasyPost Production API Key', groups=EASYPOST_CREDENTIAL_GROUPS, copy=False,
        help='Production API key from the EasyPost dashboard, used in the production environment.',
    )
    easypost_carrier_accounts = fields.Char(
        string='EasyPost Carrier Accounts',
        help='IDs of the EasyPost carrier accounts to rate with, separated by commas (e.g. ca_123, ca_456). '
             'Leave empty to rate with all the accounts of your EasyPost account.',
    )
    easypost_carrier_filter = fields.Char(
        string='EasyPost Carrier Filter',
        help='Only rates of these carriers, separated by commas, as EasyPost names them (e.g. USPS, UPS, FedEx, '
             'DHLExpress). Leave empty for all carriers.',
    )
    easypost_service_filter = fields.Char(
        string='EasyPost Service Filter',
        help='Only rates of these services, separated by commas, as EasyPost names them (e.g. Priority, '
             'GroundAdvantage, FEDEX_GROUND). Leave empty for all services.',
    )
    easypost_rate_choice = fields.Selection(
        selection=[('cheapest', 'Cheapest'), ('fastest', 'Fastest')],
        string='EasyPost Rate Choice', default='cheapest', required=True,
        help='Rate chosen among the rates that pass the filters.',
    )
    easypost_label_format = fields.Selection(
        selection=[('PDF', 'PDF'), ('ZPL', 'ZPL'), ('PNG', 'PNG')],
        string='EasyPost Label Format', default='PDF', required=True,
    )
    easypost_label_size = fields.Char(
        string='EasyPost Label Size', default='4x6',
        help='Label size supported by the carrier for the format, e.g. 4x6 or 4x8.',
    )
    easypost_package_type_id = fields.Many2one(
        'stock.package.type', string='EasyPost Package Type',
        help='Dimensions, base weight and carrier package code (e.g. FlatRateEnvelope) used when the transfer '
             'is not put in packages, and for the rates of quotations.',
    )
    easypost_contents_type = fields.Selection(
        selection=[
            ('merchandise', 'Merchandise'),
            ('gift', 'Gift'),
            ('documents', 'Documents'),
            ('returned_goods', 'Returned Goods'),
            ('sample', 'Sample'),
            ('other', 'Other'),
        ],
        string='EasyPost Contents Type', default='merchandise', required=True,
    )
    easypost_non_delivery_option = fields.Selection(
        selection=[('return', 'Return to Sender'), ('abandon', 'Abandon')],
        string='EasyPost Non Delivery', default='return', required=True,
    )
    easypost_eel_pfc = fields.Char(
        string='EasyPost EEL or PFC', default='NOEEI 30.37(a)',
        help='Exemption or filing code for exports from the US: NOEEI 30.37(a) below USD 2500, '
             'otherwise the ITN of the filing.',
    )
    easypost_customs_signer = fields.Char(
        string='EasyPost Customs Signer', help='Name of the person who certifies the customs information.',
    )

    @api.depends('delivery_type')
    def _compute_supports_shipping_insurance(self):
        super()._compute_supports_shipping_insurance()
        for carrier in self.filtered(lambda c: c.delivery_type == 'easypost'):
            carrier.supports_shipping_insurance = True

    # ---------------------------------------------------------------------
    # API
    # ---------------------------------------------------------------------

    def _easypost_api_url(self):
        url = self.env['ir.config_parameter'].sudo().get_str('om_delivery_easypost.api_url')
        return (url or EASYPOST_API_URL).rstrip('/')

    def _easypost_api_key(self):
        self.ensure_one()
        carrier = self.sudo()
        key = carrier.easypost_production_api_key if self.prod_environment else carrier.easypost_test_api_key
        if not key:
            raise UserError(self.env._(
                'Enter the EasyPost %(environment)s API key on the delivery method %(name)s.',
                environment=self.env._('production') if self.prod_environment else self.env._('test'),
                name=self.name,
            ))
        return key.strip()

    def _easypost_request(self, method, path, payload=None, params=None):
        self.ensure_one()
        url = self._easypost_api_url() + path
        if self.debug_logging:
            self.log_xml('%s %s\n%s' % (method, url, json.dumps(payload or params or {}, indent=1)), path)
        try:
            response = requests.request(
                method, url, json=payload, params=params, auth=(self._easypost_api_key(), ''),
                headers={'Accept': 'application/json'}, timeout=EASYPOST_TIMEOUT,
            )
        except requests.RequestException as e:
            raise UserError(self.env._('EasyPost could not be reached: %s', e)) from e
        if self.debug_logging:
            self.log_xml('%s %s\n%s' % (response.status_code, url, response.text[:10000]), path)
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}
        if response.status_code >= 400:
            raise UserError(self._easypost_error_message(data, response))
        return data

    def _easypost_error_message(self, data, response):
        error = data.get('error', data) if isinstance(data, dict) else {}
        message = error.get('message') if isinstance(error, dict) else ''
        details = []
        for item in (error.get('errors') or []) if isinstance(error, dict) else []:
            if isinstance(item, dict):
                text = ' '.join(str(part) for part in (item.get('field'), item.get('message')) if part)
                if item.get('suggestion'):
                    text = '%s (%s)' % (text, item['suggestion'])
                details.append(text)
            else:
                details.append(str(item))
        if details:
            message = '%s\n%s' % (message or '', '\n'.join(details))
        if not message:
            message = response.text[:500] or response.reason
        return self.env._('EasyPost error (%(code)s): %(message)s', code=response.status_code, message=message)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _easypost_weight_oz(self, weight):
        uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        ounce = self.env.ref('uom.product_uom_oz')
        return max(round(uom._compute_quantity(weight, ounce, round=False), 1), 0.1)

    def _easypost_parcel(self, package):
        parcel = {'weight': self._easypost_weight_oz(package.weight)}
        dimension = package.dimension
        if dimension['length'] and dimension['width'] and dimension['height']:
            uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()
            inch = self.env.ref('uom.product_uom_inch')
            for key, value in (('length', dimension['length']), ('width', dimension['width']),
                               ('height', dimension['height'])):
                parcel[key] = max(round(uom._compute_quantity(value, inch, round=False), 1), 0.1)
        if package.packaging_type:
            parcel['predefined_package'] = package.packaging_type
        return parcel

    @api.model
    def _easypost_address(self, partner, company_name=False):
        address = {
            'name': partner.name or partner.commercial_partner_id.name or '',
            'street1': partner.street or '',
            'street2': partner.street2 or '',
            'city': partner.city or '',
            'state': partner.state_id.code or '',
            'zip': partner.zip or '',
            'country': partner.country_id.code or '',
            'phone': partner.phone or partner.commercial_partner_id.phone or '',
            'email': partner.email or partner.commercial_partner_id.email or '',
        }
        company = company_name or (partner.commercial_partner_id.name if partner.commercial_partner_id.is_company
                                   and partner.commercial_partner_id != partner else '')
        if company:
            address['company'] = company
        return address

    def _easypost_check_address(self, partner, role):
        missing = [label for value, label in (
            (partner.street, self.env._('street')), (partner.city, self.env._('city')),
            (partner.zip, self.env._('zip')), (partner.country_id, self.env._('country')),
        ) if not value]
        if missing:
            raise UserError(self.env._(
                'The %(role)s address %(partner)s is missing: %(fields)s.',
                role=role, partner=partner.display_name, fields=', '.join(missing),
            ))

    def _easypost_to_usd(self, amount, currency, company):
        usd = self.env.ref('base.USD')
        if not currency or currency == usd:
            return amount
        return currency._convert(amount, usd, company, fields.Date.today())

    def _easypost_to_company_currency(self, amount, currency_code, company):
        currency = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', currency_code or 'USD')], limit=1) or self.env.ref('base.USD')
        if currency == company.currency_id:
            return amount
        return currency._convert(amount, company.currency_id, company, fields.Date.today())

    def _easypost_customs_info(self, packages, from_partner, currency, company):
        """Customs information of each package, when the shipment leaves the country."""
        items = []
        for package in packages:
            for commodity in package.commodities:
                product = commodity.product_id
                weight = self._easypost_weight_oz(product.weight * commodity.qty)
                value = self._easypost_to_usd(commodity.monetary_value * commodity.qty, currency, company)
                item = {
                    'description': (product.name or '')[:100],
                    'quantity': commodity.qty,
                    'value': round(max(value, 0.01), 2),
                    'weight': weight,
                    'origin_country': commodity.country_of_origin or from_partner.country_id.code,
                    'currency': 'USD',
                    'code': (product.default_code or '')[:20],
                }
                if product.hs_code:
                    item['hs_tariff_number'] = product.hs_code
                items.append(item)
        names = ', '.join(dict.fromkeys(item['description'] for item in items))
        return {
            'contents_type': self.easypost_contents_type,
            'contents_explanation': names[:255],
            'customs_certify': True,
            'customs_signer': self.easypost_customs_signer or self.env.user.name,
            'eel_pfc': self.easypost_eel_pfc or 'NOEEI 30.37(a)',
            'non_delivery_option': self.easypost_non_delivery_option,
            'restriction_type': 'none',
            'customs_items': items,
        }

    def _easypost_carrier_account_ids(self):
        return [ref.strip() for ref in (self.easypost_carrier_accounts or '').split(',') if ref.strip()]

    def _easypost_build(self, packages, from_partner, to_partner, currency, company, reference):
        """Create the shipment (one package) or the order (several packages) and return it with its rates."""
        self._easypost_check_address(from_partner, self.env._('origin'))
        self._easypost_check_address(to_partner, self.env._('delivery'))
        international = from_partner.country_id != to_partner.country_id
        options = {
            'label_format': self.easypost_label_format,
            'invoice_number': reference[:35],
            'print_custom_1': reference[:35],
        }
        if self.easypost_label_size:
            options['label_size'] = self.easypost_label_size.strip()
        shipments = []
        for package in packages:
            shipment = {'parcel': self._easypost_parcel(package), 'options': options}
            if international:
                shipment['customs_info'] = self._easypost_customs_info([package], from_partner, currency, company)
            shipments.append(shipment)
        from_address = self._easypost_address(from_partner, company_name=company.name)
        to_address = self._easypost_address(to_partner)
        account_ids = self._easypost_carrier_account_ids()
        if len(shipments) == 1:
            values = dict(shipments[0], to_address=to_address, from_address=from_address, reference=reference)
            if account_ids:
                values['carrier_accounts'] = account_ids
            data = self._easypost_request('POST', '/shipments', payload={'shipment': values})
            data['_kind'] = 'shipment'
        else:
            values = {'to_address': to_address, 'from_address': from_address, 'reference': reference,
                      'shipments': shipments}
            if account_ids:
                values['carrier_accounts'] = [{'id': account_id} for account_id in account_ids]
            data = self._easypost_request('POST', '/orders', payload={'order': values})
            data['_kind'] = 'order'
        return data

    def _easypost_select_rate(self, data):
        rates = data.get('rates') or []
        carriers = {c.strip().lower() for c in (self.easypost_carrier_filter or '').split(',') if c.strip()}
        services = {s.strip().lower() for s in (self.easypost_service_filter or '').split(',') if s.strip()}
        if carriers:
            rates = [rate for rate in rates if (rate.get('carrier') or '').lower() in carriers]
        if services:
            rates = [rate for rate in rates if (rate.get('service') or '').lower() in services]
        if not rates:
            messages = [message.get('message') for message in data.get('messages') or [] if message.get('message')]
            for shipment in data.get('shipments') or []:
                messages += [m.get('message') for m in shipment.get('messages') or [] if m.get('message')]
            raise UserError(self.env._(
                'EasyPost returned no rate for this shipment with the carriers and services of the delivery method.%s',
                ('\n' + '\n'.join(dict.fromkeys(messages))) if messages else '',
            ))

        def price(rate):
            try:
                return float(rate.get('rate'))
            except (TypeError, ValueError):
                return float('inf')

        if self.easypost_rate_choice == 'fastest':
            return min(rates, key=lambda r: (r.get('delivery_days') or r.get('est_delivery_days') or 999, price(r)))
        return min(rates, key=price)

    # ---------------------------------------------------------------------
    # Delivery methods
    # ---------------------------------------------------------------------

    def easypost_rate_shipment(self, order):
        try:
            packages = self._get_packages_from_order(order, self.easypost_package_type_id)
            from_partner = order.warehouse_id.partner_id or order.company_id.partner_id
            data = self._easypost_build(
                packages, from_partner, order.partner_shipping_id, order.currency_id, order.company_id, order.name,
            )
            rate = self._easypost_select_rate(data)
        except UserError as e:
            return {'success': False, 'price': 0.0, 'error_message': str(e), 'warning_message': False}
        price = self._easypost_to_company_currency(float(rate['rate']), rate.get('currency'), order.company_id)
        return {'success': True, 'price': price, 'error_message': False, 'warning_message': False}

    def easypost_send_shipping(self, pickings):
        return [self._easypost_ship(picking) for picking in pickings]

    def _easypost_ship(self, picking):
        self.ensure_one()
        company = picking.company_id
        currency = picking.sale_id.currency_id or company.currency_id
        packages = self._get_packages_from_picking(picking, self.easypost_package_type_id)
        from_partner = picking.picking_type_id.warehouse_id.partner_id or company.partner_id
        data = self._easypost_build(packages, from_partner, picking.partner_id, currency, company, picking.name)
        rate = self._easypost_select_rate(data)

        insurance = 0.0
        if self.shipping_insurance:
            total = sum(package.total_cost for package in packages)
            insurance = round(self._easypost_to_usd(total, company.currency_id, company) * self.shipping_insurance / 100, 2)

        if data['_kind'] == 'shipment':
            payload = {'rate': {'id': rate['id']}}
            if insurance:
                payload['insurance'] = '%.2f' % insurance
            bought = [self._easypost_request('POST', '/shipments/%s/buy' % data['id'], payload=payload)]
        else:
            order = self._easypost_request('POST', '/orders/%s/buy' % data['id'], payload={
                'carrier': rate['carrier'], 'service': rate['service'],
            })
            bought = order.get('shipments') or []
            if insurance and bought:
                share = '%.2f' % (insurance / len(bought))
                bought = [self._easypost_request('POST', '/shipments/%s/insure' % shipment['id'],
                                                 payload={'amount': share}) for shipment in bought]

        records = []
        attachments = []
        price = 0.0
        for shipment in bought:
            code = shipment.get('tracking_code')
            tracker = shipment.get('tracker') or {}
            records.append({
                'id': shipment.get('id'),
                'tracking_code': code,
                'tracker_id': tracker.get('id'),
                'public_url': tracker.get('public_url'),
            })
            selected = shipment.get('selected_rate') or rate
            fees = [fee for fee in shipment.get('fees') or [] if fee.get('charged') and not fee.get('refunded')]
            amount = sum(float(fee.get('amount') or 0) for fee in fees) if fees else float(selected.get('rate') or 0)
            price += self._easypost_to_company_currency(amount, selected.get('currency'), company)
            label = self._easypost_label(shipment)
            if label:
                extension = EASYPOST_LABEL_EXTENSIONS.get(self.easypost_label_format, 'pdf')
                attachments.append(('%s-%s.%s' % (self._get_delivery_label_prefix(), code, extension), label))

        picking.easypost_shipment_data = json.dumps(records)
        codes = [record['tracking_code'] for record in records if record['tracking_code']]
        picking.message_post(
            body=self.env._(
                'EasyPost shipment bought: %(carrier)s %(service)s, tracking %(codes)s.',
                carrier=rate.get('carrier'), service=rate.get('service'), codes=', '.join(codes),
            ),
            attachments=attachments,
        )
        return {'exact_price': price, 'tracking_number': ','.join(codes)}

    def _easypost_label(self, shipment):
        label = shipment.get('postage_label') or {}
        key = {'PDF': 'label_pdf_url', 'ZPL': 'label_zpl_url'}.get(self.easypost_label_format, 'label_url')
        url = label.get(key)
        if not url and self.easypost_label_format != 'PNG' and shipment.get('id'):
            converted = self._easypost_request('GET', '/shipments/%s/label' % shipment['id'],
                                               params={'file_format': self.easypost_label_format})
            url = (converted.get('postage_label') or {}).get(key)
        url = url or label.get('label_url')
        if not url:
            return False
        try:
            response = requests.get(url, timeout=EASYPOST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            _logger.warning('EasyPost label %s could not be downloaded: %s', url, e)
            return False
        return response.content

    def easypost_get_tracking_link(self, picking):
        records = picking._easypost_shipments()
        links = [[r['tracking_code'], r['public_url']] for r in records if r.get('public_url') and r.get('tracking_code')]
        if len(links) > 1:
            return json.dumps(links)
        return links[0][1] if links else False

    def easypost_cancel_shipment(self, pickings):
        for picking in pickings:
            statuses = []
            for record in picking._easypost_shipments():
                if not record.get('id'):
                    continue
                result = self._easypost_request('POST', '/shipments/%s/refund' % record['id'])
                statuses.append('%s: %s' % (record.get('tracking_code'), result.get('refund_status') or '-'))
            if statuses:
                picking.message_post(body=self.env._('EasyPost refund requested. %s', ', '.join(statuses)))
            picking.easypost_shipment_data = False

    def action_easypost_check_connection(self):
        self.ensure_one()
        if self.prod_environment:
            accounts = self._easypost_request('GET', '/carrier_accounts')
            if isinstance(accounts, dict):
                accounts = accounts.get('carrier_accounts') or []
            names = ['%s (%s)' % (account.get('readable') or account.get('type'), account.get('id'))
                     for account in accounts]
            message = self.env._('Connected to EasyPost. Carrier accounts: %s', ', '.join(names) or '-')
        else:
            # Carrier accounts can only be listed with a production key: check the test key on a tracker list.
            self._easypost_request('GET', '/trackers', params={'page_size': 1})
            message = self.env._('Connected to EasyPost with the test API key.')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('EasyPost'),
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }
