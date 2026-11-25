import json
import logging
import re
from datetime import timedelta

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SHIPROCKET_API_URL = 'https://apiv2.shiprocket.in/v1/external'
SHIPROCKET_TRACKING_URL = 'https://shiprocket.co/tracking/%s'
SHIPROCKET_TIMEOUT = 30
SHIPROCKET_CREDENTIAL_GROUPS = 'base.group_system,stock.group_stock_manager'


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    delivery_type = fields.Selection(
        selection_add=[('shiprocket', 'Shiprocket')],
        ondelete={'shiprocket': 'set default'},
    )
    shiprocket_email = fields.Char(
        string='Shiprocket API User Email', groups=SHIPROCKET_CREDENTIAL_GROUPS, copy=False,
        help='Email of the API user created in Shiprocket under Settings > API.',
    )
    shiprocket_password = fields.Char(
        string='Shiprocket API User Password', groups=SHIPROCKET_CREDENTIAL_GROUPS, copy=False,
    )
    shiprocket_token = fields.Char(string='Shiprocket Token', groups='base.group_system', copy=False, readonly=True)
    shiprocket_token_expiry = fields.Datetime(
        string='Shiprocket Token Expiry', groups='base.group_system', copy=False, readonly=True,
    )
    shiprocket_pickup_location = fields.Char(
        string='Shiprocket Pickup Location',
        help='Name of the pickup location, exactly as in Shiprocket under Settings > Pickup Addresses.',
    )
    shiprocket_pickup_postcode = fields.Char(
        string='Shiprocket Pickup Pincode',
        help='Pincode of the pickup location, used for the rates. Filled by Check Connection; '
             'when empty, the pincode of the warehouse is used.',
    )
    shiprocket_courier_choice = fields.Selection(
        selection=[
            ('recommended', 'Recommended by Shiprocket'),
            ('cheapest', 'Cheapest'),
            ('fastest', 'Fastest'),
            ('fixed', 'Fixed Courier'),
        ],
        string='Shiprocket Courier Choice', default='recommended', required=True,
    )
    shiprocket_courier_id = fields.Integer(
        string='Shiprocket Courier ID',
        help='Courier company ID in Shiprocket, used when the courier choice is Fixed Courier.',
    )
    shiprocket_mode = fields.Selection(
        selection=[('Surface', 'Surface'), ('Air', 'Air')],
        string='Shiprocket Mode', help='Only couriers of this mode. Leave empty for all couriers.',
    )
    shiprocket_cod_policy = fields.Selection(
        selection=[
            ('payment', 'When the order is paid on delivery'),
            ('always', 'Always'),
            ('never', 'Never'),
        ],
        string='Shiprocket COD Shipments', default='payment', required=True,
        help='When the shipment is sent as Cash on Delivery: when the order was paid with Cash on Delivery, '
             'always, or never (prepaid).',
    )
    shiprocket_package_type_id = fields.Many2one(
        'stock.package.type', string='Shiprocket Package Type',
        help='Dimensions and base weight used when the transfer is not put in packages.',
    )
    shiprocket_request_pickup = fields.Boolean(
        string='Shiprocket Request Pickup', default=True,
        help='Request the pickup from the courier when the shipment is created.',
    )
    shiprocket_manifest = fields.Boolean(
        string='Shiprocket Manifest', default=True,
        help='Generate the manifest and attach it to the transfer.',
    )

    @api.depends('delivery_type')
    def _compute_supports_cash_on_delivery(self):
        super()._compute_supports_cash_on_delivery()
        for carrier in self.filtered(lambda c: c.delivery_type == 'shiprocket'):
            carrier.supports_cash_on_delivery = True

    def write(self, vals):
        if 'shiprocket_email' in vals or 'shiprocket_password' in vals:
            vals = dict(vals, shiprocket_token=False, shiprocket_token_expiry=False)
        return super().write(vals)

    # ---------------------------------------------------------------------
    # API
    # ---------------------------------------------------------------------

    def _shiprocket_api_url(self):
        url = self.env['ir.config_parameter'].sudo().get_str('om_delivery_shiprocket.api_url')
        return (url or SHIPROCKET_API_URL).rstrip('/')

    def _shiprocket_log(self, message, func):
        if self.debug_logging:
            self.log_xml(message, func)

    def _shiprocket_get_token(self, force=False):
        self.ensure_one()
        carrier = self.sudo()
        now = fields.Datetime.now()
        if not force and carrier.shiprocket_token and carrier.shiprocket_token_expiry and \
                carrier.shiprocket_token_expiry > now:
            return carrier.shiprocket_token
        if not carrier.shiprocket_email or not carrier.shiprocket_password:
            raise UserError(self.env._(
                'Enter the email and password of your Shiprocket API user on the delivery method %s.', self.name,
            ))
        data = self._shiprocket_request('POST', '/auth/login', payload={
            'email': carrier.shiprocket_email,
            'password': carrier.shiprocket_password,
        }, auth=False)
        token = data.get('token') or (data.get('data') or {}).get('token')
        if not token:
            raise UserError(self.env._('Shiprocket did not return a token: check the API user email and password.'))
        # The token is valid for 10 days: renew it a day earlier.
        carrier.write({'shiprocket_token': token, 'shiprocket_token_expiry': now + timedelta(days=9)})
        return token

    def _shiprocket_request(self, method, path, payload=None, params=None, auth=True, retry=True):
        self.ensure_one()
        url = self._shiprocket_api_url() + path
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer %s' % self._shiprocket_get_token()
        logged = dict(payload or {})
        if 'password' in logged:
            logged['password'] = '***'
        self._shiprocket_log('%s %s\n%s' % (method, url, json.dumps(logged or params or {}, indent=1)), path)
        try:
            response = requests.request(
                method, url, json=payload, params=params, headers=headers, timeout=SHIPROCKET_TIMEOUT,
            )
        except requests.RequestException as e:
            raise UserError(self.env._('Shiprocket could not be reached: %s', e)) from e
        if response.status_code == 401 and auth and retry:
            self._shiprocket_get_token(force=True)
            return self._shiprocket_request(method, path, payload=payload, params=params, auth=auth, retry=False)
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}
        self._shiprocket_log('%s %s\n%s' % (response.status_code, url, response.text[:5000]), path)
        body_status = 0
        if isinstance(data, dict):
            for key in ('status_code', 'status'):
                if isinstance(data.get(key), int):
                    body_status = max(body_status, data[key])
        if response.status_code >= 400 or body_status >= 400:
            raise UserError(self._shiprocket_error_message(data, response))
        return data if isinstance(data, dict) else {'data': data}

    def _shiprocket_error_message(self, data, response):
        message = ''
        if isinstance(data, dict):
            message = data.get('message') or ''
            errors = data.get('errors')
            if isinstance(errors, dict):
                details = []
                for field_name, field_errors in errors.items():
                    if isinstance(field_errors, list):
                        details += [str(err) for err in field_errors]
                    else:
                        details.append('%s: %s' % (field_name, field_errors))
                if details:
                    message = '%s\n%s' % (message, '\n'.join(details))
        if not message:
            message = response.text[:500] or response.reason
        return self.env._('Shiprocket error (%(code)s): %(message)s', code=response.status_code, message=message)

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _shiprocket_weight_kg(self, weight):
        uom = self.env['product.template']._get_weight_uom_id_from_ir_config_parameter()
        kg = self.env.ref('uom.product_uom_kgm')
        return round(uom._compute_quantity(weight, kg, round=False), 3)

    def _shiprocket_dimensions_cm(self, package_type):
        uom = self.env['product.template']._get_length_uom_id_from_ir_config_parameter()
        cm = self.env.ref('uom.product_uom_cm')
        values = []
        for value in (package_type.packaging_length, package_type.width, package_type.height):
            value = uom._compute_quantity(value or 0.0, cm, round=False)
            # Shiprocket needs every dimension: 10 cm when the package type has none.
            values.append(round(max(value, 1.0) if value else 10.0, 1))
        return dict(zip(('length', 'breadth', 'height'), values))

    def _shiprocket_to_inr(self, amount, currency, company, date=None):
        inr = self.env.ref('base.INR')
        if not currency or currency == inr:
            return amount
        return currency._convert(amount, inr, company, date or fields.Date.today())

    def _shiprocket_from_inr(self, amount, company, date=None):
        inr = self.env.ref('base.INR')
        if company.currency_id == inr:
            return amount
        return inr._convert(amount, company.currency_id, company, date or fields.Date.today())

    @api.model
    def _shiprocket_phone(self, partner):
        digits = re.sub(r'\D', '', partner.phone or partner.commercial_partner_id.phone or '')
        return digits[-10:] if len(digits) > 10 else digits

    def _shiprocket_pickup_zip(self, warehouse_partner):
        return (self.shiprocket_pickup_postcode or warehouse_partner.zip or self.env.company.partner_id.zip or '').strip()

    def _shiprocket_check_address(self, partner, role):
        missing = []
        if not partner.zip:
            missing.append(self.env._('pincode'))
        if not partner.city:
            missing.append(self.env._('city'))
        if not partner.street:
            missing.append(self.env._('street'))
        if missing:
            raise UserError(self.env._(
                'The %(role)s address %(partner)s is missing: %(fields)s.',
                role=role, partner=partner.display_name, fields=', '.join(missing),
            ))

    def _shiprocket_is_cod(self, order):
        if self.shiprocket_cod_policy == 'always':
            return True
        if self.shiprocket_cod_policy == 'never' or not order:
            return False
        return bool(order.sudo().transaction_ids._filtered_pending_pay_on_delivery())

    def _shiprocket_select_courier(self, pickup_zip, delivery_zip, weight, cod, declared_value, dimensions=None):
        """Ask Shiprocket the couriers serving the two pincodes and return the one of the courier choice."""
        self.ensure_one()
        if not pickup_zip:
            raise UserError(self.env._('Set the pincode of the pickup location or of the warehouse.'))
        params = {
            'pickup_postcode': pickup_zip,
            'delivery_postcode': delivery_zip,
            'weight': weight,
            'cod': 1 if cod else 0,
            'declared_value': int(round(declared_value or 0)),
        }
        if dimensions:
            params.update({key: int(round(value)) for key, value in dimensions.items()})
        if self.shiprocket_mode:
            params['mode'] = self.shiprocket_mode
        data = self._shiprocket_request('GET', '/courier/serviceability/', params=params)
        result = data.get('data') or {}
        couriers = result.get('available_courier_companies') or []
        if not couriers:
            raise UserError(self.env._(
                'No Shiprocket courier serves pincode %(to)s from %(origin)s for this shipment.',
                to=delivery_zip, origin=pickup_zip,
            ))

        def to_float(value, default=0.0):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        choice = self.shiprocket_courier_choice
        courier = False
        if choice == 'fixed':
            courier = next((c for c in couriers if c.get('courier_company_id') == self.shiprocket_courier_id), False)
            if not courier:
                raise UserError(self.env._(
                    'The Shiprocket courier %(courier)s does not serve pincode %(to)s for this shipment.',
                    courier=self.shiprocket_courier_id, to=delivery_zip,
                ))
        elif choice == 'cheapest':
            courier = min(couriers, key=lambda c: to_float(c.get('rate'), float('inf')))
        elif choice == 'fastest':
            courier = min(couriers, key=lambda c: (
                to_float(c.get('estimated_delivery_days'), 999), to_float(c.get('rate'), float('inf'))))
        else:
            recommended = result.get('recommended_courier_company_id') or result.get('shiprocket_recommended_courier_id')
            courier = next((c for c in couriers if c.get('courier_company_id') == recommended), False) or \
                min(couriers, key=lambda c: to_float(c.get('rate'), float('inf')))
        return courier

    # ---------------------------------------------------------------------
    # Delivery methods
    # ---------------------------------------------------------------------

    def shiprocket_rate_shipment(self, order):
        partner = order.partner_shipping_id
        try:
            self._shiprocket_check_address(partner, self.env._('delivery'))
            packages = self._get_packages_from_order(order, self.shiprocket_package_type_id)
            weight = self._shiprocket_weight_kg(sum(package.weight for package in packages))
            declared = self._shiprocket_to_inr(
                order._compute_amount_total_without_delivery(), order.currency_id, order.company_id, order.date_order,
            )
            courier = self._shiprocket_select_courier(
                self._shiprocket_pickup_zip(order.warehouse_id.partner_id), partner.zip.strip(), weight,
                self._shiprocket_is_cod(order), declared, self._shiprocket_dimensions_cm(self.shiprocket_package_type_id),
            )
        except UserError as e:
            return {'success': False, 'price': 0.0, 'error_message': str(e), 'warning_message': False}
        price = self._shiprocket_from_inr(float(courier.get('rate') or 0.0), order.company_id, order.date_order)
        return {'success': True, 'price': price, 'error_message': False, 'warning_message': False}

    def shiprocket_send_shipping(self, pickings):
        return [self._shiprocket_ship(picking) for picking in pickings]

    def _shiprocket_order_items(self, picking, currency):
        items = []
        for commodity in self._get_commodities_from_stock_move_lines(picking.move_line_ids):
            product = commodity.product_id
            item = {
                'name': product.name[:200],
                'sku': (product.default_code or product.barcode or 'ID%s' % product.id)[:50],
                'units': int(commodity.qty),
                'selling_price': round(self._shiprocket_to_inr(
                    commodity.monetary_value, currency, picking.company_id), 2),
            }
            hsn = re.sub(r'\D', '', product.hs_code or '')
            if hsn:
                item['hsn'] = int(hsn)
            items.append(item)
        return items

    def _shiprocket_ship(self, picking):
        self.ensure_one()
        partner = picking.partner_id
        self._shiprocket_check_address(partner, self.env._('delivery'))
        if not self.shiprocket_pickup_location:
            raise UserError(self.env._('Set the Shiprocket pickup location on the delivery method %s.', self.name))
        order = picking.sale_id
        currency = order.currency_id or picking.company_id.currency_id
        packages = self._get_packages_from_picking(picking, self.shiprocket_package_type_id)
        weight = self._shiprocket_weight_kg(sum(package.weight for package in packages))
        biggest = self.shiprocket_package_type_id
        for package in picking.move_line_ids.result_package_id:
            package_type = package.package_type_id
            if package_type and (package_type.packaging_length * package_type.width * package_type.height) > \
                    (biggest.packaging_length * biggest.width * biggest.height):
                biggest = package_type
        dimensions = self._shiprocket_dimensions_cm(biggest)
        items = self._shiprocket_order_items(picking, currency)
        sub_total = round(sum(item['units'] * item['selling_price'] for item in items), 2)
        cod = self._shiprocket_is_cod(order)
        shipping_charges = 0.0
        if cod and order:
            shipping_charges = self._shiprocket_to_inr(
                sum(order.order_line.filtered('is_delivery').mapped('price_total')), currency, picking.company_id)

        courier = self._shiprocket_select_courier(
            self._shiprocket_pickup_zip(picking.picking_type_id.warehouse_id.partner_id), partner.zip.strip(), weight,
            cod, sub_total, dimensions,
        )

        reference = picking.name if not picking.shiprocket_order_id else '%s-%s' % (
            picking.name, picking.shiprocket_send_count + 1)
        email = partner.email or partner.commercial_partner_id.email or picking.company_id.email or ''
        payload = {
            'order_id': reference[:50],
            'order_date': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%Y-%m-%d %H:%M'),
            'pickup_location': self.shiprocket_pickup_location,
            'billing_customer_name': partner.name or partner.commercial_partner_id.name,
            'billing_last_name': '',
            'billing_address': partner.street,
            'billing_address_2': partner.street2 or '',
            'billing_city': (partner.city or '')[:30],
            'billing_pincode': partner.zip.strip(),
            'billing_state': partner.state_id.name or '',
            'billing_country': partner.country_id.name or 'India',
            'billing_email': email,
            'billing_phone': self._shiprocket_phone(partner),
            'shipping_is_billing': True,
            'order_items': items,
            'payment_method': 'COD' if cod else 'Prepaid',
            'shipping_charges': round(shipping_charges, 2),
            'sub_total': sub_total,
            'weight': weight,
            **dimensions,
        }
        if partner.commercial_partner_id.is_company and partner.commercial_partner_id != partner:
            payload['company_name'] = partner.commercial_partner_id.name
        if order:
            payload['comment'] = order.name
        data = self._shiprocket_request('POST', '/orders/create/adhoc', payload=payload)
        shipment_id = data.get('shipment_id')
        if not shipment_id:
            raise UserError(self.env._('Shiprocket did not create the shipment: %s', data.get('message') or data))
        picking.write({
            'shiprocket_order_id': str(data.get('order_id') or ''),
            'shiprocket_shipment_id': str(shipment_id),
            'shiprocket_send_count': picking.shiprocket_send_count + 1,
        })

        awb_data = self._shiprocket_request('POST', '/courier/assign/awb', payload={
            'shipment_id': shipment_id,
            'courier_id': courier.get('courier_company_id'),
        })
        awb_values = (awb_data.get('response') or {}).get('data') or {}
        awb = awb_values.get('awb_code')
        if awb_data.get('awb_assign_status') != 1 or not awb:
            raise UserError(self.env._(
                'Shiprocket could not assign an AWB: %s',
                awb_values.get('awb_assign_error') or awb_data.get('message') or awb_data,
            ))
        courier_name = awb_values.get('courier_name') or courier.get('courier_name') or ''
        picking.shiprocket_courier_name = courier_name

        notes = []
        attachments = []
        if self.shiprocket_request_pickup:
            try:
                pickup = self._shiprocket_request('POST', '/courier/generate/pickup', payload={'shipment_id': [shipment_id]})
                scheduled = (pickup.get('response') or {}).get('pickup_scheduled_date')
                if scheduled:
                    notes.append(self.env._('Pickup scheduled on %s.', scheduled))
            except UserError as e:
                notes.append(self.env._('Pickup not requested: %s', e))

        label = self._shiprocket_request('POST', '/courier/generate/label', payload={'shipment_id': [shipment_id]})
        if label.get('label_created') and label.get('label_url'):
            content = self._shiprocket_download(label['label_url'])
            if content:
                attachments.append(('%s-%s.pdf' % (self._get_delivery_label_prefix(), awb), content))
        else:
            notes.append(self.env._('Label not generated: %s', label.get('response') or ''))

        if self.shiprocket_manifest:
            manifest_url = False
            try:
                manifest = self._shiprocket_request('POST', '/manifests/generate', payload={'shipment_id': [shipment_id]})
                manifest_url = manifest.get('manifest_url')
            except UserError:
                manifest_url = False
            if not manifest_url and data.get('order_id'):
                try:
                    manifest = self._shiprocket_request('POST', '/manifests/print', payload={'order_ids': [data['order_id']]})
                    manifest_url = manifest.get('manifest_url')
                except UserError as e:
                    notes.append(self.env._('Manifest not generated: %s', e))
            if manifest_url:
                content = self._shiprocket_download(manifest_url)
                if content:
                    attachments.append(('%s-Manifest-%s.pdf' % (self._get_delivery_doc_prefix(), awb), content))

        body = self.env._(
            'Shiprocket shipment created: AWB %(awb)s with %(courier)s.', awb=awb, courier=courier_name,
        )
        if notes:
            body = '%s %s' % (body, ' '.join(notes))
        picking.message_post(body=body, attachments=attachments)

        price = self._shiprocket_from_inr(float(courier.get('rate') or 0.0), picking.company_id)
        return {'exact_price': price, 'tracking_number': awb}

    def _shiprocket_download(self, url):
        try:
            response = requests.get(url, timeout=SHIPROCKET_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as e:
            _logger.warning('Shiprocket document %s could not be downloaded: %s', url, e)
            return False
        return response.content

    def shiprocket_get_tracking_link(self, picking):
        refs = [ref.strip() for ref in (picking.carrier_tracking_ref or '').split(',') if ref.strip()]
        if len(refs) > 1:
            return json.dumps([[ref, SHIPROCKET_TRACKING_URL % ref] for ref in refs])
        return SHIPROCKET_TRACKING_URL % refs[0] if refs else False

    def shiprocket_cancel_shipment(self, pickings):
        for picking in pickings:
            if picking.shiprocket_order_id and picking.shiprocket_order_id.isdigit():
                self._shiprocket_request('POST', '/orders/cancel', payload={'ids': [int(picking.shiprocket_order_id)]})
            elif picking.carrier_tracking_ref:
                awbs = [ref.strip() for ref in picking.carrier_tracking_ref.split(',') if ref.strip()]
                self._shiprocket_request('POST', '/orders/cancel/shipment/awbs', payload={'awbs': awbs})
            picking.write({'shiprocket_shipment_id': False, 'shiprocket_courier_name': False})

    def _shiprocket_track(self, awb):
        data = self._shiprocket_request('GET', '/courier/track/awb/%s' % awb)
        return data.get('tracking_data') or {}

    def action_shiprocket_check_connection(self):
        self.ensure_one()
        self._shiprocket_get_token(force=True)
        data = self._shiprocket_request('GET', '/settings/company/pickup')
        locations = (data.get('data') or {}).get('shipping_address') or []
        names = [loc.get('pickup_location') for loc in locations if loc.get('pickup_location')]
        location = False
        if self.shiprocket_pickup_location:
            location = next((loc for loc in locations if loc.get('pickup_location') == self.shiprocket_pickup_location), False)
        elif locations:
            location = next((loc for loc in locations if loc.get('is_primary_location')), locations[0])
            self.shiprocket_pickup_location = location.get('pickup_location')
        if location and location.get('pin_code'):
            self.shiprocket_pickup_postcode = location['pin_code']
        if self.shiprocket_pickup_location and not location:
            notification_type = 'warning'
            message = self.env._(
                'Connected, but the pickup location %(name)s is not in Shiprocket. Pickup locations: %(names)s',
                name=self.shiprocket_pickup_location, names=', '.join(names) or '-',
            )
        else:
            notification_type = 'success'
            message = self.env._('Connected to Shiprocket. Pickup locations: %s', ', '.join(names) or '-')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Shiprocket'),
                'message': message,
                'type': notification_type,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
