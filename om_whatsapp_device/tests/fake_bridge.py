""" A fake WhatsApp Bridge: answers WhatsappBridge._request as the bridge of
the module does (bridge/src/server.js), and keeps what it was asked. """
from contextlib import contextmanager
from unittest.mock import patch

from odoo.addons.om_whatsapp_device.tools import BridgeError, WhatsappBridge


class FakeBridge:

    def __init__(self):
        self.running = True
        self.sessions = {}
        self.sent = []
        self.reactions = []
        self.receipts = []
        self.pictures_asked = []
        self.picture = None
        self.calls = []
        self.fail_send = None
        self.last_id = 0

    def link(self, key, me='96555551234'):
        """ The phone scans the QR code. """
        self.sessions[key].update(state='open', qr=None, pairing_code=None, me=me)

    def request(self, bridge, method, path, json=None, timeout=None):
        self.calls.append((method, path, json))
        if not self.running:
            raise BridgeError(f"The WhatsApp Bridge does not answer at {bridge.url}: start it.")
        if path == '/health':
            return {'ok': True, 'version': '1.0.0', 'sessions': list(self.sessions.values())}
        _sessions, key, *action = path.strip('/').split('/')
        session = self.sessions.setdefault(key, {'key': key, 'state': 'stopped', 'qr': None, 'pairing_code': None,
                                                 'me': None, 'reason': None})
        if action == ['start']:
            session['config'] = json
            if json.get('pairing_phone'):
                session.update(state='pairing', pairing_code='ABCD1234', qr=None)
            elif session['state'] in ('stopped', 'logged_out') or json.get('restart'):
                session.update(state='qr', qr='2@QR+DATA/1==', qr_image='data:image/png;base64,iVBORw0KGgo=')
            return {'ok': True, **session}
        if action == ['send']:
            if session['state'] != 'open':
                raise BridgeError("WhatsApp is not linked: scan the QR code in Odoo.")
            if self.fail_send:
                raise BridgeError(self.fail_send)
            self.sent.append(json)
            ids = []
            for _content in (json.get('files') or [None]):
                self.last_id += 1
                ids.append(f'OUT{self.last_id}')
            return {'ok': True, 'ids': ids}
        if action == ['picture']:
            if session['state'] != 'open':
                raise BridgeError("WhatsApp is not linked: scan the QR code in Odoo.")
            self.pictures_asked.append(json['to'])
            return {'ok': True, 'data': self.picture}
        if action == ['receipt']:
            if session['state'] != 'open':
                raise BridgeError("WhatsApp is not linked: scan the QR code in Odoo.")
            self.receipts.append(json)
            return {'ok': True}
        if action == ['react']:
            if session['state'] != 'open':
                raise BridgeError("WhatsApp is not linked: scan the QR code in Odoo.")
            self.reactions.append(json)
            return {'ok': True, 'id': 'REACT1'}
        if action == ['logout']:
            session.update(state='logged_out', me=None)
            return {'ok': True}
        return {'ok': True, **session}


@contextmanager
def fake_bridge():
    bridge = FakeBridge()

    def request(self, *args, **kwargs):
        return bridge.request(self, *args, **kwargs)

    with patch.object(WhatsappBridge, '_request', autospec=True, side_effect=request):
        yield bridge
