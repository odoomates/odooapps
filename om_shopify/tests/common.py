import json
import re
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase

REQUEST_PATH = 'odoo.addons.om_connector_base.tools.http.requests.request'


def fake_response(status=200, payload=None, headers=None):
    response = MagicMock(status_code=status, headers=headers or {})
    response.json.return_value = payload if payload is not None else {}
    response.text = json.dumps(payload) if payload is not None else ''
    return response


class FakeShopify:
    """ Answers the calls to Shopify made through ``requests.request``.

    ``graphql`` maps the name of an operation (``query OmShopifyShop``) to a list of answers, used
    in turn (the last one again and again); an answer is a dict (the JSON body, status 200), a
    ``(status, body)`` tuple, or a callable taking the variables. ``calls`` keeps every call.
    """

    def __init__(self, graphql=None, token=None, files=None):
        self.files = files or {}
        self.graphql = {name: list(answers) if isinstance(answers, list) else [answers]
                        for name, answers in (graphql or {}).items()}
        self.token = token or {'access_token': 'shpat_new', 'expires_in': 86399}
        self.calls = []

    def __call__(self, method, url, **kwargs):
        if url in self.files:
            self.calls.append(('file', url))
            response = fake_response(200)
            response.iter_lines.return_value = [line.encode() for line in self.files[url]]
            return response
        if url.endswith('/admin/oauth/access_token'):
            self.calls.append(('token', kwargs.get('data')))
            token = self.token
            if isinstance(token, tuple):
                return fake_response(*token)
            return fake_response(200, token)
        body = kwargs.get('json') or {}
        name = re.search(r'(?:query|mutation)\s+(\w+)', body.get('query', '')).group(1)
        self.calls.append((name, body.get('variables'), kwargs.get('headers', {}).get('X-Shopify-Access-Token')))
        answers = self.graphql.get(name)
        if not answers:
            raise AssertionError(f"Unexpected Shopify call {name}")
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if callable(answer):
            answer = answer(body.get('variables') or {})
        if isinstance(answer, tuple):
            return fake_response(*answer)
        return fake_response(200, answer)

    def names(self):
        return [call[0] for call in self.calls]


@contextmanager
def mock_shopify(graphql=None, token=None, files=None):
    fake = FakeShopify(graphql, token, files)
    with patch(REQUEST_PATH, side_effect=fake):
        yield fake


SHOP_ANSWER = {'data': {'shop': {
    'id': 'gid://shopify/Shop/1', 'name': 'Demo Shop', 'email': 'shop@example.com',
    'myshopifyDomain': 'demo-shop.myshopify.com', 'currencyCode': 'USD', 'ianaTimezone': 'America/New_York',
}}}

LOCATIONS_ANSWER = {'data': {'locations': {'nodes': [
    {'id': 'gid://shopify/Location/1', 'name': 'Main Warehouse', 'isActive': True, 'fulfillsOnlineOrders': True},
    {'id': 'gid://shopify/Location/2', 'name': 'Old Shop', 'isActive': False, 'fulfillsOnlineOrders': False},
], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}}


class ShopifyCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store = cls.env['om.shopify.store'].create({
            'name': 'Demo',
            'shop_domain': 'demo-shop',
            'auth_type': 'token',
            'access_token': 'shpat_test',
            'client_secret': 'webhook-secret',
            'webhook_base_url': 'https://odoo.example.com',
        })


def money(amount, currency='USD', presentment=None, presentment_currency='EUR'):
    return {'shopMoney': {'amount': str(amount), 'currencyCode': currency},
            'presentmentMoney': {'amount': str(presentment if presentment is not None else amount),
                                 'currencyCode': presentment_currency if presentment is not None else currency}}


def variant(gid, sku, price='10.00', options=None, barcode=None, inventory_item=None, tracked=True, title=None):
    return {
        'id': f'gid://shopify/ProductVariant/{gid}', 'title': title or ' / '.join(o['value'] for o in options or [])
        or 'Default Title', 'sku': sku, 'barcode': barcode, 'price': price, 'compareAtPrice': None, 'position': 1,
        'selectedOptions': options or [{'name': 'Title', 'value': 'Default Title'}],
        'inventoryItem': {'id': inventory_item or f'gid://shopify/InventoryItem/{gid}', 'tracked': tracked,
                          'measurement': {'weight': {'unit': 'GRAMS', 'value': 500}}},
    }


def product(gid, title, variants, options=None):
    return {'data': {'product': {
        'id': f'gid://shopify/Product/{gid}', 'title': title, 'handle': title.lower().replace(' ', '-'),
        'status': 'ACTIVE', 'descriptionHtml': '', 'vendor': 'Demo', 'productType': '', 'tags': [],
        'updatedAt': '2026-11-16T10:00:00Z',
        'options': options or [{'name': 'Title', 'position': 1, 'optionValues': [{'name': 'Default Title'}]}],
        'featuredMedia': None,
        'variants': {'nodes': variants, 'pageInfo': {'hasNextPage': False, 'endCursor': None}},
    }}}


def order(gid=1001, name='#1001', lines=None, financial='PAID', taxes_included=False, shipping=None, tip=0,
          total=None, cancelled=False, gateway='bogus', email='jane@example.com', **extra):
    address = {'firstName': 'Jane', 'lastName': 'Doe', 'name': 'Jane Doe', 'company': None,
               'address1': '1 Main Street', 'address2': None, 'city': 'Springfield', 'zip': '12345',
               'provinceCode': None, 'countryCodeV2': 'US', 'phone': None}
    return {'data': {'order': {
        'id': f'gid://shopify/Order/{gid}', 'name': name, 'createdAt': '2026-11-16T09:00:00Z',
        'processedAt': '2026-11-16T09:00:00Z', 'updatedAt': '2026-11-16T09:05:00Z',
        'cancelledAt': '2026-11-16T10:00:00Z' if cancelled else None, 'cancelReason': 'CUSTOMER' if cancelled else None,
        'test': True, 'email': email, 'phone': None, 'note': None, 'tags': ['web'], 'currencyCode': 'USD',
        'taxesIncluded': taxes_included, 'sourceName': 'web', 'displayFinancialStatus': financial,
        'displayFulfillmentStatus': 'UNFULFILLED', 'paymentGatewayNames': [gateway],
        'customer': {'id': 'gid://shopify/Customer/7', 'firstName': 'Jane', 'lastName': 'Doe',
                     'defaultEmailAddress': {'emailAddress': email}, 'defaultPhoneNumber': None},
        'billingAddress': address, 'shippingAddress': address,
        'totalPriceSet': money(total if total is not None else 0), 'totalTipReceivedSet': money(tip),
        'lineItems': {'nodes': lines or [], 'pageInfo': {'hasNextPage': False}},
        'shippingLines': {'nodes': shipping or []},
        'transactions': [{'id': 'gid://shopify/OrderTransaction/1', 'kind': 'SALE', 'status': 'SUCCESS',
                          'gateway': gateway, 'amountSet': money(total or 0)}],
        'refunds': [], 'risk': None, 'currentTotalDutiesSet': None, 'presentmentCurrencyCode': 'USD',
        'fulfillmentOrders': {'nodes': []},
        **extra,
    }}}


def line(gid, variant_gid, product_gid, qty, price, discount=0, taxes=None, sku=None, name='Item'):
    return {
        'id': f'gid://shopify/LineItem/{gid}', 'name': name, 'sku': sku, 'quantity': qty, 'currentQuantity': qty,
        'isGiftCard': False, 'requiresShipping': True,
        'variant': {'id': f'gid://shopify/ProductVariant/{variant_gid}'} if variant_gid else None,
        'product': {'id': f'gid://shopify/Product/{product_gid}'} if product_gid else None,
        'originalUnitPriceSet': money(price),
        'discountAllocations': [{'allocatedAmountSet': money(discount)}] if discount else [],
        'taxLines': [{'title': title, 'rate': rate, 'priceSet': money(0)} for title, rate in taxes or []],
    }
