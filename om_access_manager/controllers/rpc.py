# Odoo drops the request before an XML-RPC/JSON-RPC sign-in, so the client
# address is kept here for the Allowed Networks check.
from odoo import http
from odoo.http import request

from odoo.addons.rpc.controllers.jsonrpc import JSONRPC
from odoo.addons.rpc.controllers.xmlrpc import XMLRPC

from ..models.login_tools import RPC_ADDRESS


def with_address(serve):
    token = RPC_ADDRESS.set(request.httprequest.remote_addr)
    try:
        return serve()
    finally:
        RPC_ADDRESS.reset(token)


class XMLRPCAccess(XMLRPC):
    # a controller only takes a route over by declaring it again

    @http.route()
    def xmlrpc_1(self, service):
        return with_address(lambda: super(XMLRPCAccess, self).xmlrpc_1(service))

    @http.route()
    def xmlrpc_2(self, service):
        return with_address(lambda: super(XMLRPCAccess, self).xmlrpc_2(service))


class JSONRPCAccess(JSONRPC):

    @http.route()
    def jsonrpc(self, service, method, args):
        return with_address(lambda: super(JSONRPCAccess, self).jsonrpc(service, method, args))
