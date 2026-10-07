# The lines reported to the audit log after a transaction (refusals, ended
# sessions). The test cursors cannot show a line written after a rollback, so
# the lines are caught on their way out.
import json
from contextlib import contextmanager
from unittest.mock import patch

from odoo import tests as odoo_tests


@contextmanager
def lines_after_transaction(env):
    lines = []
    with patch.object(type(env['om.user.audit.log']), '_om_write_separately', autospec=True,
                      side_effect=lambda log, registry, vals_list: lines.extend(vals_list)):
        yield lines


def has_access(records, operation):
    """ has_access() of the later versions: the rights on the model, then the record rules. """
    from odoo.exceptions import AccessError  # noqa: PLC0415
    try:
        records.check_access_rights(operation)
        records.check_access_rule(operation)
    except AccessError:
        return False
    return True


class JsonRpcException(Exception):
    """ The error of a JSON-RPC request answering with an error, as Odoo 17 raises it. """

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class HttpCase(odoo_tests.HttpCase):
    """ HttpCase with the make_jsonrpc_request() of Odoo 17. """

    def make_jsonrpc_request(self, route, params=None, headers=None):
        data = json.dumps({'id': 0, 'jsonrpc': '2.0', 'method': 'call', 'params': params}).encode()
        headers = dict(headers or {}, **{'Content-Type': 'application/json'})
        response = self.url_open(route, data, headers=headers)
        response.raise_for_status()
        decoded = response.json()
        if 'result' in decoded:
            return decoded['result']
        if 'error' in decoded:
            raise JsonRpcException(code=decoded['error']['code'], message=decoded['error']['data']['name'])


def modifier(node, name):
    """ A modifier of a node of a view as Odoo 15 serves it: True or a domain. """
    return json.loads(node.get('modifiers') or '{}').get(name)
