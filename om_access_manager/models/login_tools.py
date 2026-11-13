# Sign-in helpers, kept free of any model so both the profile and its sign-in
# fields can import them.
import ipaddress
from datetime import datetime, timezone


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
