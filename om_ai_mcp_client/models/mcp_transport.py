"""Client side of the MCP Streamable HTTP transport (JSON-RPC 2.0 over HTTP
POST; the answer is one JSON object or a stream of server-sent events)."""
import json
import logging
import re
import time

import requests

_logger = logging.getLogger(__name__)

PROTOCOL_VERSION = '2025-11-25'
SUPPORTED_VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05')
MAX_BYTES = 10 * 1024 * 1024
MAX_RESUME = 3


class McpClientError(Exception):
    """The server could not be used: network, HTTP or protocol error."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.message = message
        self.status = status


class McpAuthRequired(McpClientError):
    """401: the server wants (new) credentials."""

    def __init__(self, message, challenge=''):
        super().__init__(message, 401)
        self.challenge = challenge or ''


class McpSessionExpired(McpClientError):
    """404 on a request with a session id: start a new session."""


class McpRpcError(McpClientError):
    """A JSON-RPC error answered by the server."""

    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = code
        self.data = data


def parse_challenge(header):
    """Parameters of a WWW-Authenticate Bearer challenge."""
    return {key.lower(): value for key, value in re.findall(r'([\w-]+)="([^"]*)"', header or '')}


class McpHttpClient:
    """One connection to an outside MCP server. ``session_id`` and
    ``protocol_version`` come from initialize and are reused."""

    def __init__(self, url, headers=None, timeout=30, session_id=None, protocol_version=None, client_info=None):
        self.url = url
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.session_id = session_id
        self.protocol_version = protocol_version
        self.client_info = client_info or {'name': 'odoo', 'version': '1.0'}
        self._next_id = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def initialize(self):
        self.session_id = None
        self.protocol_version = None
        result = self.request('initialize', {
            'protocolVersion': PROTOCOL_VERSION,
            'capabilities': {},
            'clientInfo': self.client_info,
        })
        version = result.get('protocolVersion') if isinstance(result, dict) else None
        if version not in SUPPORTED_VERSIONS:
            raise McpClientError('The server uses MCP version %s, which is not supported.' % version)
        self.protocol_version = version
        self.notify('notifications/initialized')
        return result

    def close(self):
        """End the session on the server (it may refuse with 405)."""
        if not self.session_id:
            return
        try:
            requests.delete(self.url, headers=self._headers(), timeout=min(self.timeout, 10))
        except requests.exceptions.RequestException:
            pass
        self.session_id = None

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def _headers(self, accept='application/json, text/event-stream'):
        headers = dict(self.headers)
        headers.update({'Accept': accept})
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        if self.protocol_version:
            headers['MCP-Protocol-Version'] = self.protocol_version
        return headers

    def notify(self, method, params=None):
        body = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            body['params'] = params
        response = self._post(body)
        response.close()

    def request(self, method, params=None):
        self._next_id += 1
        request_id = self._next_id
        body = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
        if params is not None:
            body['params'] = params
        response = self._post(body)
        try:
            if method == 'initialize' and response.headers.get('Mcp-Session-Id'):
                self.session_id = response.headers['Mcp-Session-Id']
            content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if content_type == 'text/event-stream':
                message = self._read_stream(response, request_id)
            elif content_type == 'application/json':
                message = self._read_json(response, request_id)
            else:
                raise McpClientError('The server answered with an unexpected content type: %s' % (
                    content_type or 'none'))
        finally:
            response.close()
        if 'error' in message:
            error = message['error'] if isinstance(message['error'], dict) else {}
            raise McpRpcError(error.get('code'), str(error.get('message') or 'Error'), error.get('data'))
        return message.get('result')

    def _post(self, body):
        headers = self._headers()
        headers['Content-Type'] = 'application/json'
        try:
            response = requests.post(self.url, data=json.dumps(body), headers=headers, timeout=self.timeout,
                                     stream=True)
        except requests.exceptions.Timeout:
            raise McpClientError('The server did not answer within %s seconds.' % self.timeout) from None
        except requests.exceptions.RequestException as error:
            raise McpClientError('The server could not be reached: %s' % error.__class__.__name__) from None
        if response.status_code in (200, 202):
            return response
        text = self._safe_text(response)
        response.close()
        if response.status_code == 401:
            raise McpAuthRequired('The server asks for authorization (401). %s' % text,
                                  response.headers.get('WWW-Authenticate'))
        if response.status_code == 404 and self.session_id and body.get('method') != 'initialize':
            raise McpSessionExpired('The session ended on the server.', 404)
        if response.status_code == 403:
            raise McpClientError('The server refused the request (403). %s' % text, 403)
        raise McpClientError('The server answered HTTP %s. %s' % (response.status_code, text), response.status_code)

    @staticmethod
    def _safe_text(response):
        try:
            data = response.json()
            if isinstance(data, dict):
                error = data.get('error')
                if isinstance(error, dict):
                    return str(error.get('message') or '')[:300]
                return str(data.get('error_description') or error or '')[:300]
        except ValueError:
            pass
        return (response.text or '')[:300]

    def _read_json(self, response, request_id):
        raw = response.raw.read(MAX_BYTES + 1, decode_content=True)
        if len(raw) > MAX_BYTES:
            raise McpClientError('The answer of the server is too large.')
        try:
            data = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            raise McpClientError('The server sent an answer that is not JSON.') from None
        if isinstance(data, list):
            data = next((item for item in data if isinstance(item, dict) and item.get('id') == request_id), None)
        if not isinstance(data, dict) or data.get('id') != request_id:
            raise McpClientError('The server answered another request.')
        return data

    # ------------------------------------------------------------------
    # Server-sent events
    # ------------------------------------------------------------------
    def _read_stream(self, response, request_id):
        """Read the events until the answer to our request arrives. If the
        server closes the stream first, resume it with GET and Last-Event-ID."""
        state = {'last_id': None, 'retry': 1000}
        for attempt in range(MAX_RESUME + 1):
            message = self._read_events(response, request_id, state)
            if message is not None:
                return message
            if not state['last_id'] or attempt == MAX_RESUME:
                break
            response.close()
            time.sleep(min(state['retry'], 10000) / 1000.0)
            headers = self._headers(accept='text/event-stream')
            headers['Last-Event-ID'] = state['last_id']
            try:
                response = requests.get(self.url, headers=headers, timeout=self.timeout, stream=True)
            except requests.exceptions.RequestException as error:
                raise McpClientError('The event stream could not be resumed: %s' % error.__class__.__name__) \
                    from None
            if response.status_code != 200:
                response.close()
                break
        raise McpClientError('The server closed the event stream without answering.')

    def _read_events(self, response, request_id, state):
        data_lines, size = [], 0
        try:
            for line in response.iter_lines(decode_unicode=True):
                if line is None:
                    continue
                size += len(line)
                if size > MAX_BYTES:
                    raise McpClientError('The answer of the server is too large.')
                if line == '':
                    message = self._dispatch_event(data_lines)
                    data_lines = []
                    if message is not None and message.get('id') == request_id and (
                            'result' in message or 'error' in message):
                        return message
                    continue
                if line.startswith(':'):
                    continue
                field, _sep, value = line.partition(':')
                value = value[1:] if value.startswith(' ') else value
                if field == 'data':
                    data_lines.append(value)
                elif field == 'id':
                    state['last_id'] = value
                elif field == 'retry' and value.isdigit():
                    state['retry'] = int(value)
        except requests.exceptions.RequestException:
            pass  # connection lost: resume if possible
        message = self._dispatch_event(data_lines)
        if message is not None and message.get('id') == request_id and ('result' in message or 'error' in message):
            return message
        return None

    def _dispatch_event(self, data_lines):
        if not data_lines:
            return None
        text = '\n'.join(data_lines)
        if not text.strip():
            return None  # priming event
        try:
            message = json.loads(text)
        except ValueError:
            _logger.debug('MCP client: event that is not JSON ignored')
            return None
        if not isinstance(message, dict):
            return None
        if 'method' in message and 'id' in message:
            self._answer_server_request(message)
            return None
        return message

    def _answer_server_request(self, message):
        """The server asks something (ping, sampling, ...): answer ping, refuse
        the rest, so the server does not wait."""
        if message.get('method') == 'ping':
            answer = {'jsonrpc': '2.0', 'id': message['id'], 'result': {}}
        else:
            answer = {'jsonrpc': '2.0', 'id': message['id'],
                      'error': {'code': -32601, 'message': 'Not supported by this client'}}
        try:
            response = self._post(answer)
            response.close()
        except McpClientError:
            _logger.debug('MCP client: could not answer a server request')
