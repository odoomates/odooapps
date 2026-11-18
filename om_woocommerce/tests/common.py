import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from odoo.tests import TransactionCase

REQUEST_PATH = 'odoo.addons.om_connector_base.tools.http.requests.request'
SITE = 'https://shop.example.com'


def fake_response(status=200, payload=None, headers=None):
    response = MagicMock(status_code=status, headers=headers or {})
    if isinstance(payload, str):
        response.json.side_effect = ValueError('not JSON')
        response.text = payload
    else:
        response.json.return_value = payload if payload is not None else {}
        response.text = json.dumps(payload) if payload is not None else ''
    return response


class _Sequence(tuple):
    """ Answers given in turn for one route. """


def sequence(*answers):
    return _Sequence(answers)


class FakeWoo:
    """ Answers the calls to WooCommerce made through ``requests.request``.

    ``routes`` maps ``"METHOD path"`` (``"GET orders/1001"``, ``"POST products/batch"``; the path
    after ``/wp-json/wc/v3/``, or after ``/wp-json/`` for another namespace, ``/`` for the index)
    to an answer. An answer is a body (status
    200), a ``(status, body)`` or ``(status, body, headers)`` tuple, or a callable taking
    ``(params, json)``; ``sequence(a, b)`` gives its answers in turn, the last one again and again.
    ``calls`` keeps ``(method, path, params, json)`` of every call. """

    def __init__(self, routes=None, files=None):
        self.routes = {key: list(answers) if isinstance(answers, _Sequence) else [answers]
                       for key, answers in (routes or {}).items()}
        self.files = files or {}
        self.calls = []

    def __call__(self, method, url, **kwargs):
        if url in self.files:
            self.calls.append(('FILE', url, None, None))
            response = fake_response(200)
            response.ok, response.content = True, self.files[url]
            return response
        parsed = urlparse(url)
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        if 'rest_route' in query:
            route = query['rest_route']
        else:
            route = parsed.path.split('/wp-json', 1)[1] if '/wp-json' in parsed.path else parsed.path
        route = route.strip('/')
        path = route[len('wc/v3/'):] if route.startswith('wc/v3/') else route
        path = path or '/'
        params = {**query, **(kwargs.get('params') or {})}
        body = kwargs.get('json')
        self.calls.append((method, path, params, body))
        key = f'{method} {path}'
        if key not in self.routes:
            raise AssertionError(f"Unexpected WooCommerce call {key}")
        answers = self.routes[key]
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        if callable(answer):
            answer = answer(params, body)
        if isinstance(answer, tuple):
            return fake_response(*answer)
        return fake_response(200, answer)

    def paths(self, method=None):
        return [f'{c[0]} {c[1]}' for c in self.calls if method is None or c[0] == method]

    def bodies(self, key):
        return [c[3] for c in self.calls if f'{c[0]} {c[1]}' == key]


@contextmanager
def mock_woo(routes=None, files=None):
    fake = FakeWoo(routes, files)
    with patch(REQUEST_PATH, side_effect=fake):
        yield fake


INDEX = {'name': 'Demo Shop', 'description': 'Just another shop', 'url': SITE, 'timezone_string': 'Europe/Brussels',
         'namespaces': ['oembed/1.0', 'wc/v3', 'wc/store/v1', 'wp/v2']}


class WooCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.store = cls.env['om.woocommerce.store'].create({
            'name': 'Demo',
            'site_url': 'shop.example.com',
            'consumer_key': 'ck_test',
            'consumer_secret': 'cs_test',
            'webhook_base_url': 'https://odoo.example.com',
        })


def address(**values):
    return {'first_name': 'Jane', 'last_name': 'Doe', 'company': '', 'address_1': '1 Main Street', 'address_2': '',
            'city': 'Springfield', 'state': '', 'postcode': '12345', 'country': 'US',
            'email': 'jane@example.com', 'phone': '555-0100', **values}


def item(item_id, product_id, qty, subtotal, total=None, variation_id=0, taxes=None, sku='', name='Item'):
    """ An order line; ``taxes``: ``[(rate id, tax total)]``. """
    total = subtotal if total is None else total
    return {
        'id': item_id, 'name': name, 'product_id': product_id, 'variation_id': variation_id, 'quantity': qty,
        'subtotal': f'{subtotal:.2f}', 'total': f'{total:.2f}',
        'subtotal_tax': f'{sum(t for _r, t in taxes or []) * (subtotal / total if total else 1):.2f}',
        'total_tax': f'{sum(t for _r, t in taxes or []):.2f}',
        'taxes': [{'id': rate, 'total': f'{tax:.2f}', 'subtotal': f'{tax:.2f}'} for rate, tax in taxes or []],
        'sku': sku, 'price': total / qty if qty else 0, 'meta_data': [],
    }


def order(order_id=1001, status='processing', items=None, total=0.0, paid=True, include_tax=False, shipping=None,
          fees=None, tax_lines=None, customer_id=0, method='stripe', refunds=None, **extra):
    return {
        'id': order_id, 'number': str(order_id), 'status': status, 'currency': 'USD',
        'prices_include_tax': include_tax, 'date_created_gmt': '2026-11-16T09:00:00',
        'date_modified_gmt': '2026-11-16T09:05:00', 'date_paid_gmt': '2026-11-16T09:01:00' if paid else None,
        'total': f'{total:.2f}', 'customer_id': customer_id, 'customer_note': '',
        'billing': address(), 'shipping': address(email=None, phone=''),
        'payment_method': method, 'payment_method_title': method.title(), 'transaction_id': 'ch_1',
        'created_via': 'checkout', 'line_items': items or [], 'shipping_lines': shipping or [],
        'fee_lines': fees or [], 'coupon_lines': [], 'tax_lines': tax_lines or [], 'refunds': refunds or [],
        'meta_data': [], **extra,
    }


def tax_line(rate_id, percent, label='Tax'):
    return {'id': 900 + rate_id, 'rate_code': f'US-{label}-1', 'rate_id': rate_id, 'label': label,
            'compound': False, 'tax_total': '0', 'shipping_tax_total': '0', 'rate_percent': percent}


def simple_product(product_id, name, sku, price='10.00', manage_stock=True, **extra):
    return {'id': product_id, 'name': name, 'slug': name.lower().replace(' ', '-'), 'type': 'simple',
            'status': 'publish', 'sku': sku, 'global_unique_id': '', 'price': price, 'regular_price': price,
            'weight': '500', 'manage_stock': manage_stock, 'stock_quantity': 7, 'images': [], 'attributes': [],
            'variations': [], 'parent_id': 0, **extra}
