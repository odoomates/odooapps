import base64
import json
import logging
import re
import time

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ARAMEX_PRODUCTION_URL = 'https://ws.aramex.net/ShippingAPI.V2'
ARAMEX_TEST_URL = 'https://ws.dev.aramex.net/ShippingAPI.V2'
ARAMEX_TRACKING_URL = 'https://www.aramex.com/track/results?ShipmentNumber=%s'
ARAMEX_TIMEOUT = 45
ARAMEX_CREDENTIAL_GROUPS = 'base.group_system,stock.group_stock_manager'


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('aramex', 'Aramex')],
        ondelete={'aramex': 'set default'},
    )
    aramex_username = fields.Char(string='Aramex Username', groups=ARAMEX_CREDENTIAL_GROUPS, copy=False)
    aramex_password = fields.Char(string='Aramex Password', groups=ARAMEX_CREDENTIAL_GROUPS, copy=False)
    aramex_account_number = fields.Char(string='Aramex Account Number', groups=ARAMEX_CREDENTIAL_GROUPS, copy=False)
    aramex_account_pin = fields.Char(string='Aramex Account PIN', groups=ARAMEX_CREDENTIAL_GROUPS, copy=False)
    aramex_account_entity = fields.Char(
        string='Aramex Account Entity', groups=ARAMEX_CREDENTIAL_GROUPS, copy=False,
        help='Three letter code of the Aramex office of your account, e.g. DXB, RUH, AMM.',
    )
    aramex_account_country_code = fields.Char(
        string='Aramex Account Country', groups=ARAMEX_CREDENTIAL_GROUPS, copy=False,
        help='Two letter country code of your account, e.g. AE, SA, JO.',
    )
    aramex_product_group = fields.Selection(
        selection=[('auto', 'Automatic'), ('EXP', 'Express (international)'), ('DOM', 'Domestic')],
        string='Aramex Product Group', default='auto', required=True,
        help='Automatic: Domestic when the shipment stays in the country, Express otherwise.',
    )
    aramex_product_type_exp = fields.Selection(
        selection=[
            ('PPX', 'PPX - Priority Parcel Express'),
            ('PDX', 'PDX - Priority Document Express'),
            ('PLX', 'PLX - Priority Letter Express'),
            ('DPX', 'DPX - Deferred Parcel Express'),
            ('DDX', 'DDX - Deferred Document Express'),
            ('GPX', 'GPX - Ground Parcel Express'),
            ('GDX', 'GDX - Ground Document Express'),
            ('EPX', 'EPX - Economy Parcel Express'),
        ],
        string='Aramex Express Product', default='PPX', required=True,
    )
    aramex_product_type_dom = fields.Char(
        string='Aramex Domestic Product', default='ONP',
        help='Product type code for domestic shipments as given by Aramex, e.g. ONP (overnight parcel), '
             'OND (overnight document), CDS.',
    )
    aramex_payment_type = fields.Selection(
        selection=[('P', 'Prepaid'), ('C', 'Collect')],
        string='Aramex Payment Type', default='P', required=True,
        help='Prepaid: the freight is charged to your account. Collect: the consignee pays the freight.',
    )
    aramex_payment_options = fields.Char(
        string='Aramex Payment Options',
        help='Payment option code for Collect shipments when Aramex asks for one, e.g. CASH, ACCT.',
    )
    aramex_cod_policy = fields.Selection(
        selection=[
            ('payment', 'When the order is paid on delivery'),
            ('always', 'Always'),
            ('never', 'Never'),
        ],
        string='Aramex COD Shipments', default='payment', required=True,
        help='When the shipment is sent as Cash on Delivery (service CODS): when the order was paid with Cash '
             'on Delivery, always, or never.',
    )
    aramex_label_report_id = fields.Integer(
        string='Aramex Label Report', default=9201,
        help='Report ID of the label layout given by Aramex: 9201 is the standard label.',
    )
    aramex_package_type_id = fields.Many2one(
        'stock.package.type', string='Aramex Package Type',
        help='Dimensions and base weight used when the transfer is not put in packages.',
    )
    aramex_description_of_goods = fields.Char(
        string='Aramex Goods Description',
        help='Description of the goods on the AWB. Leave empty to use the names of the products.',
    )

    @api.depends('delivery_type')
    def _compute_supports_cash_on_delivery(self):
        super()._compute_supports_cash_on_delivery()
        for carrier in self.filtered(lambda c: c.delivery_type == 'aramex'):
            carrier.supports_cash_on_delivery = True

    # ---------------------------------------------------------------------
    # API
    # ---------------------------------------------------------------------

    def _aramex_api_url(self):
        url = self.env['ir.config_parameter'].sudo().get_str('om_delivery_aramex.api_url')
        return (url or (ARAMEX_PRODUCTION_URL if self.prod_environment else ARAMEX_TEST_URL)).rstrip('/')

    def _aramex_client_info(self):
        self.ensure_one()
        carrier = self.sudo()
        values = {
            'UserName': carrier.aramex_username,
            'Password': carrier.aramex_password,
            'Version': 'v1.0',
            'AccountNumber': carrier.aramex_account_number,
            'AccountPin': carrier.aramex_account_pin,
            'AccountEntity': (carrier.aramex_account_entity or '').upper(),
            'AccountCountryCode': (carrier.aramex_account_country_code or '').upper(),
            'Source': 24,
        }
        if not all(values.values()):
            raise UserError(self.env._('Enter all the Aramex credentials on the delivery method %s.', self.name))
        return values

    @api.model
    def _aramex_transaction(self, reference=''):
        return {'Reference1': (reference or '')[:50], 'Reference2': '', 'Reference3': '', 'Reference4': '',
                'Reference5': ''}

    def _aramex_request(self, service, operation, payload):
        self.ensure_one()
        url = '%s/%s/Service_1_0.svc/json/%s' % (self._aramex_api_url(), service, operation)
        payload = dict(payload, ClientInfo=self._aramex_client_info())
        if self.debug_logging:
            logged = dict(payload, ClientInfo=dict(payload['ClientInfo'], Password='***', AccountPin='***'))
            self.log_xml('POST %s\n%s' % (url, json.dumps(logged, indent=1)), operation)
        try:
            response = requests.post(url, json=payload, headers={'Accept': 'application/json'}, timeout=ARAMEX_TIMEOUT)
        except requests.RequestException as e:
            raise UserError(self.env._('Aramex could not be reached: %s', e)) from e
        if self.debug_logging:
            self.log_xml('%s %s\n%s' % (response.status_code, url, response.text[:10000]), operation)
        try:
            data = response.json()
        except ValueError:
            raise UserError(self.env._(
                'Aramex error (%(code)s): %(message)s', code=response.status_code,
                message=re.sub(r'<[^>]+>', ' ', response.text or '')[:500].strip() or response.reason,
            )) from None
        if response.status_code >= 400 or data.get('HasErrors'):
            raise UserError(self.env._('Aramex error: %s', self._aramex_notifications(data) or response.reason))
        return data

    @api.model
    def _aramex_notifications(self, data):
        messages = ['%s %s' % (n.get('Code') or '', n.get('Message') or '') for n in data.get('Notifications') or []]
        for shipment in data.get('Shipments') or []:
            if isinstance(shipment, dict):
                messages += ['%s %s' % (n.get('Code') or '', n.get('Message') or '')
                             for n in shipment.get('Notifications') or []]
        return '\n'.join(message.strip() for message in messages if message.strip())

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _aramex_weight_kg(self, weight):
        uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        return max(round(uom._compute_quantity(weight, self.env.ref('uom.product_uom_kgm'), round=False), 3), 0.01)

    def _aramex_dimensions(self, package_type):
        if not (package_type.packaging_length and package_type.width and package_type.height):
            return None
        uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()
        cm = self.env.ref('uom.product_uom_cm')
        return {
            'Length': round(uom._compute_quantity(package_type.packaging_length, cm, round=False), 1),
            'Width': round(uom._compute_quantity(package_type.width, cm, round=False), 1),
            'Height': round(uom._compute_quantity(package_type.height, cm, round=False), 1),
            'Unit': 'cm',
        }

    @api.model
    def _aramex_address(self, partner):
        return {
            'Line1': partner.street or '',
            'Line2': partner.street2 or '',
            'Line3': '',
            'City': partner.city or '',
            'StateOrProvinceCode': partner.state_id.code or '',
            'PostCode': partner.zip or '',
            'CountryCode': partner.country_id.code or '',
        }

    def _aramex_party(self, partner, account_number='', company_name=''):
        phone = partner.phone or partner.commercial_partner_id.phone or ''
        commercial = partner.commercial_partner_id
        return {
            'Reference1': '',
            'Reference2': '',
            'AccountNumber': account_number,
            'PartyAddress': self._aramex_address(partner),
            'Contact': {
                'Department': '',
                'PersonName': partner.name or commercial.name or '',
                'Title': '',
                'CompanyName': company_name or (commercial.name if commercial.is_company else partner.name) or '',
                'PhoneNumber1': phone,
                'PhoneNumber1Ext': '',
                'PhoneNumber2': '',
                'PhoneNumber2Ext': '',
                'FaxNumber': '',
                'CellPhone': phone,
                'EmailAddress': partner.email or commercial.email or '',
                'Type': '',
            },
        }

    def _aramex_check_address(self, partner, role):
        missing = [label for value, label in (
            (partner.street, self.env._('street')), (partner.city, self.env._('city')),
            (partner.country_id, self.env._('country')),
        ) if not value]
        if missing:
            raise UserError(self.env._(
                'The %(role)s address %(partner)s is missing: %(fields)s.',
                role=role, partner=partner.display_name, fields=', '.join(missing),
            ))

    def _aramex_product(self, from_partner, to_partner):
        group = self.aramex_product_group
        if group == 'auto':
            group = 'DOM' if from_partner.country_id == to_partner.country_id else 'EXP'
        product_type = self.aramex_product_type_exp if group == 'EXP' else (self.aramex_product_type_dom or 'ONP')
        return group, product_type

    def _aramex_is_cod(self, order):
        if self.aramex_cod_policy == 'always':
            return True
        if self.aramex_cod_policy == 'never' or not order:
            return False
        return bool(order.sudo().transaction_ids._filtered_pending_pay_on_delivery())

    @api.model
    def _aramex_money(self, amount, currency):
        return {'Value': round(amount, 2), 'CurrencyCode': currency.name}

    @api.model
    def _aramex_date(self, offset_days=0):
        return '/Date(%d)/' % int((time.time() + offset_days * 86400) * 1000)

    def _aramex_details(self, packages, from_partner, to_partner, currency, order=False):
        group, product_type = self._aramex_product(from_partner, to_partner)
        package_type = self.aramex_package_type_id
        for package in packages:
            if package.dimension['length'] and package.dimension['width'] and package.dimension['height']:
                package_type = self.env['stock.package.type'].new({
                    'packaging_length': package.dimension['length'],
                    'width': package.dimension['width'],
                    'height': package.dimension['height'],
                })
                break
        commodities = [commodity for package in packages for commodity in package.commodities]
        names = ', '.join(dict.fromkeys(c.product_id.name for c in commodities if c.product_id.name))
        value = sum(c.monetary_value * c.qty for c in commodities)
        weight = self._aramex_weight_kg(sum(package.weight for package in packages))
        services = []
        cod_amount = None
        if self._aramex_is_cod(order):
            services.append('CODS')
            amount = order.amount_total if order else value
            cod_amount = self._aramex_money(amount, currency)
        items = []
        if group == 'EXP':
            for commodity in commodities:
                product = commodity.product_id
                items.append({
                    'PackageType': 'Box',
                    'Quantity': int(commodity.qty),
                    'Weight': {'Value': self._aramex_weight_kg(product.weight * commodity.qty), 'Unit': 'KG'},
                    'Comments': '',
                    'Reference': (product.default_code or '')[:50],
                    'GoodsDescription': (product.name or '')[:100],
                    'CountryOfOrigin': commodity.country_of_origin or from_partner.country_id.code or '',
                    'CustomsValue': self._aramex_money(commodity.monetary_value * commodity.qty, currency),
                    'CommodityCode': product.hs_code or '',
                })
        return {
            'Dimensions': self._aramex_dimensions(package_type),
            'ActualWeight': {'Value': weight, 'Unit': 'KG'},
            'ChargeableWeight': None,
            'DescriptionOfGoods': (self.aramex_description_of_goods or names or self.env._('Goods'))[:100],
            'GoodsOriginCountry': from_partner.country_id.code or '',
            'NumberOfPieces': max(len(packages), 1),
            'ProductGroup': group,
            'ProductType': product_type,
            'PaymentType': self.aramex_payment_type,
            'PaymentOptions': self.aramex_payment_options or '' if self.aramex_payment_type == 'C' else '',
            'CustomsValueAmount': self._aramex_money(value, currency) if group == 'EXP' else None,
            'CashOnDeliveryAmount': cod_amount,
            'InsuranceAmount': None,
            'CashAdditionalAmount': None,
            'CashAdditionalAmountDescription': '',
            'CollectAmount': None,
            'Services': ','.join(services),
            'Items': items,
        }

    def _aramex_to_company_currency(self, amount, currency_code, company):
        currency = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', currency_code)], limit=1) if currency_code else company.currency_id
        if not currency or currency == company.currency_id:
            return amount
        return currency._convert(amount, company.currency_id, company, fields.Date.today())

    # ---------------------------------------------------------------------
    # Delivery methods
    # ---------------------------------------------------------------------

    def aramex_rate_shipment(self, order):
        from_partner = order.warehouse_id.partner_id or order.company_id.partner_id
        to_partner = order.partner_shipping_id
        try:
            self._aramex_check_address(from_partner, self.env._('origin'))
            self._aramex_check_address(to_partner, self.env._('delivery'))
            packages = self._get_packages_from_order(order, self.aramex_package_type_id)
            data = self._aramex_request('RateCalculator', 'CalculateRate', {
                'Transaction': self._aramex_transaction(order.name),
                'OriginAddress': self._aramex_address(from_partner),
                'DestinationAddress': self._aramex_address(to_partner),
                'ShipmentDetails': self._aramex_details(packages, from_partner, to_partner, order.currency_id, order),
                'PreferredCurrencyCode': order.company_id.currency_id.name,
            })
        except UserError as e:
            return {'success': False, 'price': 0.0, 'error_message': str(e), 'warning_message': False}
        total = data.get('TotalAmount') or {}
        price = self._aramex_to_company_currency(float(total.get('Value') or 0.0), total.get('CurrencyCode'),
                                                 order.company_id)
        return {'success': True, 'price': price, 'error_message': False, 'warning_message': False}

    def aramex_send_shipping(self, pickings):
        return [self._aramex_ship(picking) for picking in pickings]

    def _aramex_ship(self, picking):
        self.ensure_one()
        company = picking.company_id
        order = picking.sale_id
        currency = order.currency_id or company.currency_id
        from_partner = picking.picking_type_id.warehouse_id.partner_id or company.partner_id
        to_partner = picking.partner_id
        self._aramex_check_address(from_partner, self.env._('origin'))
        self._aramex_check_address(to_partner, self.env._('delivery'))
        packages = self._get_packages_from_picking(picking, self.aramex_package_type_id)
        details = self._aramex_details(packages, from_partner, to_partner, currency, order)
        account_number = self.sudo().aramex_account_number
        shipment = {
            'Reference1': picking.name,
            'Reference2': order.name or '',
            'Reference3': '',
            'Shipper': self._aramex_party(from_partner, account_number, company.name),
            'Consignee': self._aramex_party(to_partner),
            'ThirdParty': None,
            'ShippingDateTime': self._aramex_date(),
            'DueDate': self._aramex_date(1),
            'Comments': '',
            'PickupLocation': '',
            'OperationsInstructions': '',
            'AccountingInstrcutions': '',
            'Details': details,
            'Attachments': [],
            'ForeignHAWB': '',
            'PickupGUID': '',
            'Number': None,
            'ScheduledDelivery': None,
        }
        label_info = {'ReportID': self.aramex_label_report_id or 9201, 'ReportType': 'URL'}
        data = self._aramex_request('Shipping', 'CreateShipments', {
            'Transaction': self._aramex_transaction(picking.name),
            'LabelInfo': label_info,
            'Shipments': [shipment],
        })
        result = (data.get('Shipments') or [{}])[0]
        if result.get('HasErrors') or not result.get('ID'):
            raise UserError(self.env._('Aramex did not create the shipment: %s', self._aramex_notifications(data)))
        awb = str(result['ID'])
        label = self._aramex_label_content(result.get('ShipmentLabel') or {})
        if not label:
            label = self._aramex_print_label(awb, details['ProductGroup'])
        attachments = [('%s-%s.pdf' % (self._get_delivery_label_prefix(), awb), label)] if label else []
        picking.message_post(
            body=self.env._(
                'Aramex shipment created: AWB %(awb)s, %(group)s %(type)s, %(pieces)s piece(s).',
                awb=awb, group=details['ProductGroup'], type=details['ProductType'], pieces=details['NumberOfPieces'],
            ),
            attachments=attachments,
        )
        price = 0.0
        try:
            rate = self._aramex_request('RateCalculator', 'CalculateRate', {
                'Transaction': self._aramex_transaction(picking.name),
                'OriginAddress': self._aramex_address(from_partner),
                'DestinationAddress': self._aramex_address(to_partner),
                'ShipmentDetails': details,
                'PreferredCurrencyCode': company.currency_id.name,
            })
            total = rate.get('TotalAmount') or {}
            price = self._aramex_to_company_currency(float(total.get('Value') or 0.0), total.get('CurrencyCode'), company)
        except UserError as e:
            _logger.info('Aramex rate of %s not available: %s', picking.name, e)
        return {'exact_price': price, 'tracking_number': awb}

    def _aramex_label_content(self, label):
        if label.get('LabelFileContents'):
            content = label['LabelFileContents']
            if isinstance(content, list):
                return bytes(content)
            try:
                return base64.b64decode(content)
            except (ValueError, TypeError):
                return False
        if label.get('LabelURL'):
            try:
                response = requests.get(label['LabelURL'], timeout=ARAMEX_TIMEOUT)
                response.raise_for_status()
            except requests.RequestException as e:
                _logger.warning('Aramex label %s could not be downloaded: %s', label['LabelURL'], e)
                return False
            return response.content
        return False

    def _aramex_print_label(self, awb, product_group):
        try:
            data = self._aramex_request('Shipping', 'PrintLabel', {
                'Transaction': self._aramex_transaction(awb),
                'ShipmentNumber': awb,
                'ProductGroup': product_group,
                'OriginEntity': (self.sudo().aramex_account_entity or '').upper(),
                'LabelInfo': {'ReportID': self.aramex_label_report_id or 9201, 'ReportType': 'URL'},
            })
        except UserError as e:
            _logger.warning('Aramex label of %s not printed: %s', awb, e)
            return False
        return self._aramex_label_content(data.get('ShipmentLabel') or {})

    def aramex_get_tracking_link(self, picking):
        refs = [ref.strip() for ref in (picking.carrier_tracking_ref or '').split(',') if ref.strip()]
        if len(refs) > 1:
            return json.dumps([[ref, ARAMEX_TRACKING_URL % ref] for ref in refs])
        return ARAMEX_TRACKING_URL % refs[0] if refs else False

    def aramex_cancel_shipment(self, pickings):
        # The Aramex shipping services cancel pickups, not shipments: the AWB is voided by Aramex.
        for picking in pickings:
            picking.message_post(body=self.env._(
                'The Aramex API has no cancellation of shipments: ask Aramex to cancel AWB %s.',
                picking.carrier_tracking_ref,
            ))

    def _aramex_track(self, awbs):
        data = self._aramex_request('Tracking', 'TrackShipments', {
            'Transaction': self._aramex_transaction(),
            'Shipments': awbs,
            'GetLastTrackingUpdateOnly': True,
        })
        return {result.get('Key'): result.get('Value') or [] for result in data.get('TrackingResults') or []}

    def action_aramex_check_connection(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        partner = company.partner_id
        self._aramex_request('RateCalculator', 'CalculateRate', {
            'Transaction': self._aramex_transaction('check'),
            'OriginAddress': self._aramex_address(partner),
            'DestinationAddress': self._aramex_address(partner),
            'ShipmentDetails': {
                'Dimensions': None,
                'ActualWeight': {'Value': 0.5, 'Unit': 'KG'},
                'ChargeableWeight': None,
                'DescriptionOfGoods': 'Check',
                'GoodsOriginCountry': partner.country_id.code or '',
                'NumberOfPieces': 1,
                'ProductGroup': 'DOM',
                'ProductType': self.aramex_product_type_dom or 'ONP',
                'PaymentType': 'P',
                'PaymentOptions': '',
                'CustomsValueAmount': None,
                'CashOnDeliveryAmount': None,
                'InsuranceAmount': None,
                'CashAdditionalAmount': None,
                'CashAdditionalAmountDescription': '',
                'CollectAmount': None,
                'Services': '',
                'Items': [],
            },
            'PreferredCurrencyCode': company.currency_id.name,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Aramex'),
                'message': self.env._('Connected to Aramex: a test rate was calculated.'),
                'type': 'success',
                'sticky': False,
            },
        }
