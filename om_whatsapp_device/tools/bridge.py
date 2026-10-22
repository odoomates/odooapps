""" The WhatsApp Bridge of this module (bridge/ in it): a Node.js program on
the server that keeps the linked devices connected. Every call goes through
``WhatsappBridge._request``: the tests replace it with a fake bridge. """
import requests

TIMEOUT = 10
# sending waits for the pause of a person between two messages, and the upload
SEND_TIMEOUT = 120


class BridgeError(Exception):
    pass


class WhatsappBridge:

    def __init__(self, url, secret):
        self.url = (url or '').rstrip('/')
        self.secret = secret

    def _request(self, method, path, json=None, timeout=TIMEOUT):
        try:
            response = requests.request(method, f'{self.url}{path}', json=json, timeout=timeout,
                                        headers={'Authorization': f'Bearer {self.secret}'})
        except requests.RequestException as error:
            raise BridgeError(f"The WhatsApp Bridge does not answer at {self.url}: start it.") from error
        try:
            answer = response.json()
        except ValueError:
            answer = {}
        if response.status_code == 403:
            raise BridgeError("The WhatsApp Bridge refused the secret: it must be the one shown on the account.")
        if not answer.get('ok'):
            raise BridgeError(answer.get('error') or f"The WhatsApp Bridge answered {response.status_code}.")
        return answer

    def health(self):
        return self._request('GET', '/health')

    def start(self, key, **config):
        return self._request('POST', f'/sessions/{key}/start', json=config)

    def status(self, key):
        return self._request('GET', f'/sessions/{key}')

    def send(self, key, to, text='', files=(), quoted=False):
        """ The ids WhatsApp gave the messages sent; ``quoted`` ({id, from_me}): the message they answer. """
        payload = {'to': to, 'text': text, 'files': list(files)}
        if quoted:
            payload['quoted'] = quoted
        answer = self._request('POST', f'/sessions/{key}/send', json=payload, timeout=SEND_TIMEOUT)
        return answer.get('ids') or []

    def react(self, key, to, message_id, from_me, emoji=''):
        """ React to a message of the chat of ``to``; an empty emoji takes it back. """
        return self._request('POST', f'/sessions/{key}/react',
                             json={'to': to, 'id': message_id, 'from_me': from_me, 'emoji': emoji})

    def receipt(self, key, to, message_ids, kind='read'):
        """ The messages of the chat of ``to`` read, or played (voice messages). """
        return self._request('POST', f'/sessions/{key}/receipt', json={'to': to, 'ids': list(message_ids), 'kind': kind})

    def picture(self, key, to):
        """ The profile picture of ``to``, in base64; None when it shows none. """
        return self._request('POST', f'/sessions/{key}/picture', json={'to': to}).get('data')

    def logout(self, key):
        return self._request('POST', f'/sessions/{key}/logout')
