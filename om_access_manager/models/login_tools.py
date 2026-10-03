# Sign-in helpers, kept free of any model so both the profile and its sign-in
# fields can import them.
import contextvars
import ipaddress
from datetime import datetime, timezone

# XML-RPC and JSON-RPC drop the request before signing in, so their controllers
# keep the client address here (controllers/rpc.py)
RPC_ADDRESS = contextvars.ContextVar('om_access_rpc_address', default=None)


def utc_now():
    """ The current time; a function of its own so that tests can patch it. """
    return datetime.now(timezone.utc)


def parse_networks(text):
    """ Parse one address or network per line; blank lines and ``#`` comments are ignored. """
    networks = []
    for line in (text or '').splitlines():
        line = line.split('#')[0].strip()
        if line:
            networks.append(ipaddress.ip_network(line, strict=False))
    return tuple(networks)


def client_address():
    """ The address the current request comes from, RPC included. """
    from odoo.http import request  # noqa: PLC0415
    if request:
        return request.httprequest.remote_addr
    return RPC_ADDRESS.get()
