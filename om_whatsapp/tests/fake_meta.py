""" A fake Meta: answers MetaApi._request as the Graph API does, after its
documentation, and keeps what it was asked. """
from contextlib import contextmanager
from unittest.mock import patch

from odoo.addons.om_whatsapp.tools import MetaApi, MetaApiError

APP_ID = '1234567890'
APP_SECRET = 'app-secret'
TOKEN = 'EAAG-good-token'
PERMANENT_TOKEN = 'EAAG-system-user-token'
WABA_ID = '1029384756'
PHONE_ID = '5550001111'


class FakeMeta:

    def __init__(self):
        self.tokens = {TOKEN: {
            'is_valid': True,
            'expires_at': 1893456000,
            'scopes': ['whatsapp_business_management', 'whatsapp_business_messaging', 'business_management'],
            'granular_scopes': [
                {'scope': 'whatsapp_business_management', 'target_ids': [WABA_ID]},
                {'scope': 'whatsapp_business_messaging', 'target_ids': [WABA_ID]},
            ],
        }}
        self.numbers = [
            {'id': PHONE_ID, 'display_phone_number': '+1 555-000-1111', 'verified_name': 'Odoo Mates',
             'quality_rating': 'GREEN', 'code_verification_status': 'VERIFIED', 'messaging_limit_tier': 'TIER_1K'},
            {'id': '5550002222', 'display_phone_number': '+1 555-000-2222', 'verified_name': 'Test Number',
             'quality_rating': 'GREEN', 'code_verification_status': 'NOT_VERIFIED', 'messaging_limit_tier': 'TIER_250'},
        ]
        self.tokens[PERMANENT_TOKEN] = {**self.tokens[TOKEN], 'expires_at': 0}
        self.calls = []
        self.sent = []
        self.uploads = []
        self.registered = {}
        self.subscribed = []
        self.webhook = None
        self.fail_send = None
        self.last_id = 0
        self.templates = []
        self.samples = []

    def request(self, api, method, path, params=None, json=None, token=None, files=None, data=None, headers=None):
        self.calls.append((method, path))
        token = token or api.access_token
        if token == f'{APP_ID}|{APP_SECRET}':
            app = True
        elif token in self.tokens:
            app = False
        else:
            raise MetaApiError('Invalid OAuth access token - Cannot parse access token', 190)
        if path == 'debug_token':
            info = self.tokens.get(params['input_token'], {'is_valid': False, 'error': {'message': 'Session has expired'}})
            if info.get('app_id', APP_ID) != APP_ID:
                raise MetaApiError('(#100) The App_id in the input_token did not match the Viewing App', 100)
            return {'data': info}
        if path == 'app' and not app:
            app_id = self.tokens[token].get('app_id', APP_ID)
            return {'id': app_id, 'name': 'Odoo Mates WhatsApp' if app_id == APP_ID else 'Other App'}
        if path == APP_ID and app:
            return {'id': APP_ID, 'name': 'Odoo Mates WhatsApp'}
        if path == f'{APP_ID}/subscriptions':
            if method == 'POST':
                self.webhook = dict(data)
                return {'success': True}
            return {'data': [{'object': 'whatsapp_business_account', 'callback_url': self.webhook['callback_url']}]
                    if self.webhook else []}
        if app:
            raise MetaApiError('An access token of a user or system user is needed', 200)
        if path == WABA_ID:
            return {'id': WABA_ID, 'name': 'Odoo Mates Business'}
        if path == f'{WABA_ID}/phone_numbers':
            return {'data': self.numbers}
        if path == f'{APP_ID}/uploads':
            return {'id': f'upload:{params["file_name"]}'}
        if path.startswith('upload:'):
            self.samples.append((path, headers.get('Authorization')))
            return {'h': f'handle-{len(self.samples)}'}
        if path == f'{WABA_ID}/message_templates':
            if method == 'GET':
                return {'data': self.templates}
            if any(t['name'] == json['name'] and t['language'] == json['language'] for t in self.templates):
                raise MetaApiError('Message template already exists with that name and language', 100, 2388023)
            template = {'id': f'tpl-{len(self.templates) + 1}', 'status': 'PENDING', **json}
            self.templates.append(template)
            return {'id': template['id'], 'status': 'PENDING', 'category': json['category']}
        if any(path == t['id'] for t in self.templates):
            template = next(t for t in self.templates if t['id'] == path)
            template.update(json, status='PENDING')
            return {'success': True}
        if path == f'{WABA_ID}/subscribed_apps':
            self.subscribed.append(WABA_ID)
            return {'success': True}
        number = next((n for n in self.numbers if path.startswith(n['id'])), None)
        if number and path == number['id']:
            return number
        if number and path.endswith('/register'):
            self.registered[number['id']] = json['pin']
            return {'success': True}
        if number and path.endswith('/media'):
            self.uploads.append(files['file'][0])
            return {'id': f'media-{len(self.uploads)}'}
        if number and path.endswith('/messages'):
            if self.fail_send:
                raise MetaApiError(*self.fail_send)
            self.sent.append({key: value for key, value in json.items() if key != 'messaging_product'})
            if json.get('status') == 'read':
                return {'success': True}
            self.last_id += 1
            return {'messaging_product': 'whatsapp', 'contacts': [{'wa_id': json['to']}],
                    'messages': [{'id': f'wamid.{self.last_id}'}]}
        if path.startswith('media-in-'):
            return {'url': f'https://lookaside.example.com/{path}', 'mime_type': 'image/jpeg', 'id': path}
        raise MetaApiError(f'Unsupported request {method} {path}', 100)


@contextmanager
def fake_meta():
    meta = FakeMeta()

    def request(api, *args, **kwargs):
        return meta.request(api, *args, **kwargs)

    with patch.object(MetaApi, '_request', autospec=True, side_effect=request):
        yield meta
