""" The WhatsApp Cloud API of Meta (Graph API), as documented on
developers.facebook.com/docs/whatsapp/cloud-api. Every call goes through
``MetaApi._request``: the tests replace it with a fake Meta. """
import logging

import requests

_logger = logging.getLogger(__name__)

GRAPH_URL = 'https://graph.facebook.com'
# a version of the Graph API lives two years; ir.config_parameter
# om_whatsapp.graph_version moves to a newer one without a new module
GRAPH_VERSION = 'v23.0'
TIMEOUT = 20


class MetaApiError(Exception):
    """ An error of Meta, with its code, as its documentation lists them. """

    def __init__(self, message, code=None, subcode=None, trace_id=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.trace_id = trace_id


class MetaApi:

    def __init__(self, env, access_token=None, app_id=None, app_secret=None):
        self.env = env
        self.access_token = access_token
        self.app_id = app_id
        self.app_secret = app_secret

    @property
    def version(self):
        return self.env['ir.config_parameter'].sudo().get_param('om_whatsapp.graph_version') or GRAPH_VERSION

    @property
    def app_token(self):
        return f'{self.app_id}|{self.app_secret}'

    def _request(self, method, path, params=None, json=None, token=None, files=None, data=None, headers=None):
        """ One call to the Graph API: the decoded answer, or MetaApiError. """
        url = f'{GRAPH_URL}/{self.version}/{path.lstrip("/")}'
        headers = {'Authorization': f'Bearer {token or self.access_token}', **(headers or {})}
        try:
            response = requests.request(method, url, params=params, json=json, files=files, data=data,
                                        headers=headers, timeout=TIMEOUT)
        except requests.RequestException as error:
            # not the error itself: it holds the url, and some urls hold the token
            raise MetaApiError(f"Meta could not be reached ({type(error).__name__}).") from error
        try:
            answer = response.json()
        except ValueError:
            answer = {}
        if response.ok and 'error' not in answer:
            return answer
        error = answer.get('error') or {}
        message = error.get('error_user_msg') or error.get('message') or response.reason
        _logger.info("Meta %s %s: %s", method, path, error or response.status_code)
        raise MetaApiError(message, error.get('code'), error.get('error_subcode'), error.get('fbtrace_id'))

    # ------------------------------------------------------------
    # SETUP
    # ------------------------------------------------------------

    def debug_token(self):
        """ What the access token is: valid, its permissions, and the business
        accounts it may manage (granular_scopes target_ids). """
        answer = self._request('GET', 'debug_token', params={'input_token': self.access_token}, token=self.app_token)
        return answer.get('data') or {}

    def get_app(self):
        """ The app of the App ID, read with the App Secret: both are right. """
        return self._request('GET', self.app_id, params={'fields': 'id,name'}, token=self.app_token)

    def get_token_app(self):
        """ The app the access token was made for. """
        return self._request('GET', 'app', params={'fields': 'id,name'})

    def get_business_account(self, waba_id):
        return self._request('GET', waba_id, params={'fields': 'id,name,currency,timezone_id'})

    def get_phone_numbers(self, waba_id):
        fields = 'id,display_phone_number,verified_name,quality_rating,code_verification_status,messaging_limit_tier'
        return self._request('GET', f'{waba_id}/phone_numbers', params={'fields': fields}).get('data') or []

    def get_phone_number(self, phone_number_id):
        fields = 'id,display_phone_number,verified_name,quality_rating,code_verification_status,messaging_limit_tier'
        return self._request('GET', phone_number_id, params={'fields': fields})

    def register_phone_number(self, phone_number_id, pin):
        return self._request('POST', f'{phone_number_id}/register', json={'messaging_product': 'whatsapp', 'pin': pin})

    def subscribe_app(self, waba_id):
        """ The app gets the webhooks of this business account. """
        return self._request('POST', f'{waba_id}/subscribed_apps')

    def set_webhook(self, callback_url, verify_token, fields):
        """ Where Meta sends the webhooks of the app. Meta calls the callback
        at once with the verify token, before answering. """
        return self._request('POST', f'{self.app_id}/subscriptions', token=self.app_token, data={
            'object': 'whatsapp_business_account',
            'callback_url': callback_url,
            'verify_token': verify_token,
            'fields': ','.join(fields),
        })

    def get_webhook(self):
        return self._request('GET', f'{self.app_id}/subscriptions', token=self.app_token).get('data') or []

    # ------------------------------------------------------------
    # MESSAGES
    # ------------------------------------------------------------

    def send_message(self, phone_number_id, payload):
        """ Send one message: the id Meta gave it (wamid). """
        answer = self._request('POST', f'{phone_number_id}/messages', json={'messaging_product': 'whatsapp', **payload})
        return (answer.get('messages') or [{}])[0].get('id')

    def mark_read(self, phone_number_id, message_id):
        """ The message (and the ones before it) read: blue ticks for the sender. """
        self._request('POST', f'{phone_number_id}/messages',
                      json={'messaging_product': 'whatsapp', 'status': 'read', 'message_id': message_id})

    def upload_media(self, phone_number_id, name, content, mimetype):
        """ Upload a file for a message: its media id. """
        answer = self._request('POST', f'{phone_number_id}/media', data={'messaging_product': 'whatsapp', 'type': mimetype},
                               files={'file': (name, content, mimetype)})
        return answer.get('id')

    def download_media(self, media_id):
        """ The file of a message received: (content, mimetype). """
        media = self._request('GET', media_id)
        try:
            response = requests.get(media['url'], headers={'Authorization': f'Bearer {self.access_token}'}, timeout=TIMEOUT)
            response.raise_for_status()
        except (KeyError, requests.RequestException) as error:
            raise MetaApiError(f"The file could not be downloaded from Meta: {error}") from error
        return response.content, media.get('mime_type') or response.headers.get('Content-Type')

    # ------------------------------------------------------------
    # TEMPLATES
    # ------------------------------------------------------------

    def get_templates(self, waba_id):
        fields = 'id,name,status,language,category,components,rejected_reason'
        templates, params = [], {'fields': fields, 'limit': 100}
        while True:
            answer = self._request('GET', f'{waba_id}/message_templates', params=params)
            templates += answer.get('data') or []
            after = ((answer.get('paging') or {}).get('cursors') or {}).get('after')
            if not after or not (answer.get('paging') or {}).get('next'):
                return templates
            params = {**params, 'after': after}

    def create_template(self, waba_id, payload):
        """ Submit a template for approval: {id, status, category}. """
        return self._request('POST', f'{waba_id}/message_templates', json=payload)

    def edit_template(self, template_id, payload):
        """ Submit the changes of an approved or rejected template again. """
        return self._request('POST', template_id, json=payload)

    def upload_sample(self, name, content, mimetype):
        """ A sample file for the review of a template with a file header:
        the handle Meta gives it, through the resumable upload of the app. """
        session = self._request('POST', f'{self.app_id}/uploads', params={
            'file_name': name, 'file_length': len(content), 'file_type': mimetype})
        answer = self._request('POST', session['id'], data=content, headers={
            'Authorization': f'OAuth {self.access_token}', 'file_offset': '0'})
        return answer.get('h')
