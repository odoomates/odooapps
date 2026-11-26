"""Request builders and response parsers for the supported AI APIs.

Every adapter turns the normalised om_ai message list into the payload of one
API and turns the API answer back into the normalised result:

    message: {'role': 'system' | 'user' | 'assistant' | 'tool',
              'content': str,
              'images': [{'mime_type': 'image/png', 'data': '<base64>'}],
              'tool_calls': [{'id': str, 'name': str, 'arguments': dict}],
              'tool_call_id': str, 'name': str}
    result:  {'text': str, 'tool_calls': [...], 'json': object | None,
              'usage': {'prompt_tokens': int, 'completion_tokens': int, 'total_tokens': int},
              'finish_reason': str}

Plain HTTP only: the engine sends what the adapter builds with requests.
"""

import json
import re

JSON_TOOL_NAME = 'json_output'

# presets that use max_completion_tokens and accept stream_options
OPENAI_STYLE_PRESETS = {'openai', 'azure'}
NO_STREAM_OPTIONS_PRESETS = {'mistral', 'perplexity'}


def _loads(value, default=None):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or '')
    except (TypeError, ValueError):
        return default


def parse_json_text(text):
    """Return the JSON object found in a model answer (code fences allowed)."""
    if not text:
        return None
    text = text.strip()
    fence = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fence:
        text = fence.group(1).strip()
    value = _loads(text)
    if value is None:
        match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if match:
            value = _loads(match.group(1))
    return value


def error_message(data, fallback=''):
    """Extract the provider's error text from an error body."""
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict):
        err = data.get('error', data)
        if isinstance(err, dict):
            msg = err.get('message') or err.get('msg') or err.get('detail')
            if msg:
                return str(msg)
        elif isinstance(err, str):
            return err
        if data.get('detail'):
            return str(data['detail'])
        if data.get('message'):
            return str(data['message'])
    return fallback


def iter_sse(lines):
    """Yield the decoded JSON payloads of a server-sent events stream."""
    for line in lines:
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode('utf-8', 'replace')
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if not payload or payload == '[DONE]':
            continue
        value = _loads(payload)
        if value is not None:
            yield value


def _usage(prompt, completion):
    prompt = int(prompt or 0)
    completion = int(completion or 0)
    return {'prompt_tokens': prompt, 'completion_tokens': completion, 'total_tokens': prompt + completion}


class BaseAdapter:
    """Common parts; one subclass per API family."""

    def __init__(self, config):
        # config: api_type, preset, base_url, api_key, extra_headers (dict), api_version
        self.config = config
        self.base_url = (config.get('base_url') or '').rstrip('/')
        self.api_key = config.get('api_key') or ''
        self.preset = config.get('preset') or 'custom'

    def headers(self):
        headers = {'Content-Type': 'application/json'}
        headers.update(self.auth_headers())
        headers.update(self.config.get('extra_headers') or {})
        return headers

    def auth_headers(self):
        return {}

    # chat -----------------------------------------------------------------
    def chat_request(self, model, messages, tools=None, json_schema=None,
                     max_tokens=None, temperature=None, stream=False):
        raise NotImplementedError

    def parse_chat(self, data):
        raise NotImplementedError

    def parse_stream(self, lines, on_delta=None):
        raise NotImplementedError

    # models ---------------------------------------------------------------
    def models_request(self):
        return self.base_url + '/models'

    def parse_models(self, data):
        raise NotImplementedError

    # embeddings -------------------------------------------------------------
    def embed_request(self, model, texts):
        raise NotImplementedError

    def parse_embed(self, data):
        raise NotImplementedError

    @staticmethod
    def finish(text, tool_calls, usage, finish_reason, json_schema=None, json_value=None):
        if json_schema and json_value is None:
            json_value = parse_json_text(text)
        return {
            'text': text or '',
            'tool_calls': tool_calls,
            'json': json_value,
            'usage': usage,
            'finish_reason': finish_reason or '',
        }


# ---------------------------------------------------------------------------
# OpenAI compatible: OpenAI, Mistral, Groq, DeepSeek, xAI, OpenRouter, Together,
# Perplexity, Ollama, LM Studio, vLLM, LocalAI and any compatible endpoint.
# ---------------------------------------------------------------------------
class OpenAIAdapter(BaseAdapter):

    def auth_headers(self):
        return {'Authorization': 'Bearer %s' % self.api_key} if self.api_key else {}

    def chat_url(self, model):
        return self.base_url + '/chat/completions'

    @staticmethod
    def convert_messages(messages):
        result = []
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content') or ''
            if role == 'tool':
                result.append({'role': 'tool', 'tool_call_id': msg.get('tool_call_id') or '', 'content': content})
            elif role == 'assistant' and msg.get('tool_calls'):
                result.append({
                    'role': 'assistant',
                    'content': content or None,
                    'tool_calls': [{
                        'id': call['id'],
                        'type': 'function',
                        'function': {'name': call['name'], 'arguments': json.dumps(call.get('arguments') or {})},
                    } for call in msg['tool_calls']],
                })
            elif msg.get('images'):
                parts = [{'type': 'text', 'text': content}] if content else []
                for image in msg['images']:
                    parts.append({'type': 'image_url', 'image_url': {
                        'url': 'data:%s;base64,%s' % (image.get('mime_type') or 'image/png', image['data'])}})
                result.append({'role': role, 'content': parts})
            else:
                result.append({'role': role, 'content': content})
        return result

    def chat_request(self, model, messages, tools=None, json_schema=None,
                     max_tokens=None, temperature=None, stream=False):
        payload = {'model': model, 'messages': self.convert_messages(messages)}
        if tools:
            payload['tools'] = [{'type': 'function', 'function': {
                'name': tool['name'],
                'description': tool.get('description') or '',
                'parameters': tool.get('parameters') or {'type': 'object', 'properties': {}},
            }} for tool in tools]
        if json_schema:
            payload['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'output', 'schema': json_schema}}
        if max_tokens:
            key = 'max_completion_tokens' if self.preset in OPENAI_STYLE_PRESETS else 'max_tokens'
            payload[key] = max_tokens
        if temperature is not None:
            payload['temperature'] = temperature
        if stream:
            payload['stream'] = True
            if self.preset not in NO_STREAM_OPTIONS_PRESETS:
                payload['stream_options'] = {'include_usage': True}
        return self.chat_url(model), payload

    @staticmethod
    def _text(content):
        if isinstance(content, list):
            return ''.join(part.get('text', '') for part in content if isinstance(part, dict))
        return content or ''

    def parse_chat(self, data, json_schema=None):
        choices = data.get('choices') or [{}]
        message = choices[0].get('message') or {}
        tool_calls = [{
            'id': call.get('id') or 'call_%s' % index,
            'name': (call.get('function') or {}).get('name') or '',
            'arguments': _loads((call.get('function') or {}).get('arguments'), {}),
        } for index, call in enumerate(message.get('tool_calls') or [])]
        usage = data.get('usage') or {}
        return self.finish(self._text(message.get('content')), tool_calls,
                           _usage(usage.get('prompt_tokens'), usage.get('completion_tokens')),
                           choices[0].get('finish_reason'), json_schema)

    def parse_stream(self, lines, on_delta=None, json_schema=None):
        text, calls, usage, finish_reason = [], {}, {}, ''
        for chunk in iter_sse(lines):
            if chunk.get('error'):
                raise ValueError(error_message(chunk))
            if chunk.get('usage'):
                usage = chunk['usage']
            for choice in chunk.get('choices') or []:
                delta = choice.get('delta') or {}
                piece = self._text(delta.get('content'))
                if piece:
                    text.append(piece)
                    if on_delta:
                        on_delta(piece)
                for call in delta.get('tool_calls') or []:
                    slot = calls.setdefault(call.get('index', len(calls)), {'id': '', 'name': '', 'arguments': ''})
                    slot['id'] = call.get('id') or slot['id']
                    function = call.get('function') or {}
                    slot['name'] += function.get('name') or ''
                    slot['arguments'] += function.get('arguments') or ''
                finish_reason = choice.get('finish_reason') or finish_reason
        tool_calls = [{
            'id': slot['id'] or 'call_%s' % index,
            'name': slot['name'],
            'arguments': _loads(slot['arguments'], {}),
        } for index, slot in sorted(calls.items())]
        return self.finish(''.join(text), tool_calls,
                           _usage(usage.get('prompt_tokens'), usage.get('completion_tokens')),
                           finish_reason, json_schema)

    def parse_models(self, data):
        items = data.get('data') if isinstance(data, dict) else data
        models = []
        for item in items or []:
            model_id = item.get('id') or item.get('name')
            if not model_id:
                continue
            vals = {'model_id': model_id, 'name': item.get('name') or item.get('display_name') or model_id}
            context = item.get('context_length') or item.get('context_window') or item.get('max_model_len')
            if context:
                vals['context_size'] = int(context)
            pricing = item.get('pricing') or {}
            try:
                if 'prompt' in pricing:  # price per token
                    vals['input_price'] = float(pricing['prompt']) * 1e6
                    vals['output_price'] = float(pricing.get('completion') or 0) * 1e6
                elif 'input' in pricing:  # price per million tokens
                    vals['input_price'] = float(pricing['input'])
                    vals['output_price'] = float(pricing.get('output') or 0)
            except (TypeError, ValueError):
                pass
            arch = item.get('architecture') or {}
            if 'image' in (arch.get('input_modalities') or []):
                vals['cap_vision'] = True
            params = item.get('supported_parameters')
            if params is not None:
                vals['cap_tools'] = 'tools' in params
            models.append(vals)
        return models

    def embed_url(self, model):
        return self.base_url + '/embeddings'

    def embed_request(self, model, texts):
        return self.embed_url(model), {'model': model, 'input': texts}

    def parse_embed(self, data):
        rows = sorted(data.get('data') or [], key=lambda row: row.get('index', 0))
        usage = data.get('usage') or {}
        return [row.get('embedding') for row in rows], _usage(usage.get('prompt_tokens'), 0)


class AzureOpenAIAdapter(OpenAIAdapter):
    """Azure OpenAI: the v1 API (base URL ending in /openai/v1) or the
    deployment routes with an api-version; the model is the deployment name."""

    def auth_headers(self):
        return {'api-key': self.api_key} if self.api_key else {}

    def _is_v1(self):
        return self.base_url.endswith('/openai/v1')

    def _deployment_url(self, model, route):
        version = self.config.get('api_version') or '2024-10-21'
        return '%s/openai/deployments/%s/%s?api-version=%s' % (self.base_url, model, route, version)

    def chat_url(self, model):
        return self.base_url + '/chat/completions' if self._is_v1() else self._deployment_url(model, 'chat/completions')

    def embed_url(self, model):
        return self.base_url + '/embeddings' if self._is_v1() else self._deployment_url(model, 'embeddings')

    def models_request(self):
        if self._is_v1():
            return self.base_url + '/models'
        return '%s/openai/models?api-version=%s' % (self.base_url, self.config.get('api_version') or '2024-10-21')


# ---------------------------------------------------------------------------
# Anthropic Messages API
# ---------------------------------------------------------------------------
class AnthropicAdapter(BaseAdapter):
    API_VERSION = '2023-06-01'
    DEFAULT_MAX_TOKENS = 4096

    def auth_headers(self):
        headers = {'anthropic-version': self.API_VERSION}
        if self.api_key:
            headers['x-api-key'] = self.api_key
        return headers

    @staticmethod
    def convert_messages(messages):
        system, result = [], []

        def add(role, blocks):
            if result and result[-1]['role'] == role:
                result[-1]['content'].extend(blocks)
            else:
                result.append({'role': role, 'content': blocks})

        for msg in messages:
            role = msg.get('role')
            content = msg.get('content') or ''
            if role == 'system':
                system.append(content)
            elif role == 'tool':
                add('user', [{'type': 'tool_result', 'tool_use_id': msg.get('tool_call_id') or '',
                              'content': content}])
            elif role == 'assistant':
                blocks = [{'type': 'text', 'text': content}] if content else []
                for call in msg.get('tool_calls') or []:
                    blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['name'],
                                   'input': call.get('arguments') or {}})
                if blocks:
                    add('assistant', blocks)
            else:
                blocks = [{'type': 'image', 'source': {
                    'type': 'base64', 'media_type': image.get('mime_type') or 'image/png', 'data': image['data'],
                }} for image in msg.get('images') or []]
                blocks.append({'type': 'text', 'text': content or '.'})
                add('user', blocks)
        return '\n\n'.join(part for part in system if part), result

    def chat_request(self, model, messages, tools=None, json_schema=None,
                     max_tokens=None, temperature=None, stream=False):
        system, converted = self.convert_messages(messages)
        payload = {'model': model, 'messages': converted, 'max_tokens': max_tokens or self.DEFAULT_MAX_TOKENS}
        if system:
            payload['system'] = system
        api_tools = [{
            'name': tool['name'],
            'description': tool.get('description') or '',
            'input_schema': tool.get('parameters') or {'type': 'object', 'properties': {}},
        } for tool in tools or []]
        if json_schema:
            api_tools.append({'name': JSON_TOOL_NAME, 'description': 'Return the answer as JSON.',
                              'input_schema': json_schema})
            payload['tool_choice'] = {'type': 'tool', 'name': JSON_TOOL_NAME}
        if api_tools:
            payload['tools'] = api_tools
        if temperature is not None:
            payload['temperature'] = temperature
        if stream:
            payload['stream'] = True
        return self.base_url + '/messages', payload

    def _split(self, blocks, json_schema):
        text, tool_calls, json_value = [], [], None
        for block in blocks:
            if block.get('type') == 'text':
                text.append(block.get('text') or '')
            elif block.get('type') == 'tool_use':
                if json_schema and block.get('name') == JSON_TOOL_NAME:
                    json_value = block.get('input')
                else:
                    tool_calls.append({'id': block.get('id'), 'name': block.get('name'),
                                       'arguments': block.get('input') or {}})
        if json_value is not None and not text:
            text = [json.dumps(json_value)]
        return ''.join(text), tool_calls, json_value

    def parse_chat(self, data, json_schema=None):
        text, tool_calls, json_value = self._split(data.get('content') or [], json_schema)
        usage = data.get('usage') or {}
        return self.finish(text, tool_calls, _usage(usage.get('input_tokens'), usage.get('output_tokens')),
                           data.get('stop_reason'), json_schema, json_value)

    def parse_stream(self, lines, on_delta=None, json_schema=None):
        blocks, prompt, completion, stop_reason = {}, 0, 0, ''
        for event in iter_sse(lines):
            kind = event.get('type')
            if kind == 'error':
                raise ValueError(error_message(event))
            if kind == 'message_start':
                usage = (event.get('message') or {}).get('usage') or {}
                prompt = usage.get('input_tokens') or prompt
                completion = usage.get('output_tokens') or completion
            elif kind == 'content_block_start':
                block = dict(event.get('content_block') or {})
                block['_json'] = ''
                blocks[event.get('index', len(blocks))] = block
            elif kind == 'content_block_delta':
                block = blocks.setdefault(event.get('index', 0), {'type': 'text', 'text': '', '_json': ''})
                delta = event.get('delta') or {}
                if delta.get('type') == 'text_delta':
                    block['text'] = (block.get('text') or '') + delta.get('text', '')
                    if on_delta:
                        on_delta(delta.get('text', ''))
                elif delta.get('type') == 'input_json_delta':
                    block['_json'] += delta.get('partial_json', '')
            elif kind == 'message_delta':
                usage = event.get('usage') or {}
                completion = usage.get('output_tokens') or completion
                prompt = usage.get('input_tokens') or prompt
                stop_reason = (event.get('delta') or {}).get('stop_reason') or stop_reason
        ordered = []
        for _index, block in sorted(blocks.items()):
            if block.get('type') == 'tool_use' and block.get('_json'):
                block['input'] = _loads(block['_json'], {})
            ordered.append(block)
        text, tool_calls, json_value = self._split(ordered, json_schema)
        return self.finish(text, tool_calls, _usage(prompt, completion), stop_reason, json_schema, json_value)

    def models_request(self):
        return self.base_url + '/models?limit=1000'

    def parse_models(self, data):
        return [{
            'model_id': item['id'],
            'name': item.get('display_name') or item['id'],
            'cap_vision': True,
            'cap_tools': True,
            'cap_json': True,
        } for item in data.get('data') or [] if item.get('id')]


# ---------------------------------------------------------------------------
# Google Gemini generateContent
# ---------------------------------------------------------------------------
class GeminiAdapter(BaseAdapter):

    def auth_headers(self):
        return {'x-goog-api-key': self.api_key} if self.api_key else {}

    @staticmethod
    def model_path(model):
        return model if model.startswith(('models/', 'tunedModels/')) else 'models/%s' % model

    @staticmethod
    def convert_messages(messages):
        system, contents = [], []

        def add(role, parts):
            if contents and contents[-1]['role'] == role:
                contents[-1]['parts'].extend(parts)
            else:
                contents.append({'role': role, 'parts': parts})

        for msg in messages:
            role = msg.get('role')
            content = msg.get('content') or ''
            if role == 'system':
                system.append({'text': content})
            elif role == 'tool':
                response = _loads(content)
                if not isinstance(response, dict):
                    response = {'result': response if response is not None else content}
                part = {'functionResponse': {'name': msg.get('name') or '', 'response': response}}
                if msg.get('tool_call_id') and not str(msg['tool_call_id']).startswith('call_'):
                    part['functionResponse']['id'] = msg['tool_call_id']
                add('user', [part])
            elif role == 'assistant':
                parts = [{'text': content}] if content else []
                for call in msg.get('tool_calls') or []:
                    function_call = {'name': call['name'], 'args': call.get('arguments') or {}}
                    if call.get('id') and not str(call['id']).startswith('call_'):
                        function_call['id'] = call['id']
                    part = {'functionCall': function_call}
                    if call.get('signature'):
                        part['thoughtSignature'] = call['signature']
                    parts.append(part)
                if parts:
                    add('model', parts)
            else:
                parts = [{'inlineData': {'mimeType': image.get('mime_type') or 'image/png', 'data': image['data']}}
                         for image in msg.get('images') or []]
                parts.append({'text': content or '.'})
                add('user', parts)
        return system, contents

    def chat_request(self, model, messages, tools=None, json_schema=None,
                     max_tokens=None, temperature=None, stream=False):
        system, contents = self.convert_messages(messages)
        payload = {'contents': contents}
        if system:
            payload['systemInstruction'] = {'parts': system}
        if tools:
            payload['tools'] = [{'functionDeclarations': [{
                'name': tool['name'],
                'description': tool.get('description') or '',
                'parametersJsonSchema': tool.get('parameters') or {'type': 'object', 'properties': {}},
            } for tool in tools]}]
        config = {}
        if max_tokens:
            config['maxOutputTokens'] = max_tokens
        if temperature is not None:
            config['temperature'] = temperature
        if json_schema:
            config['responseMimeType'] = 'application/json'
            config['responseJsonSchema'] = json_schema
        if config:
            payload['generationConfig'] = config
        method = 'streamGenerateContent?alt=sse' if stream else 'generateContent'
        return '%s/%s:%s' % (self.base_url, self.model_path(model), method), payload

    @staticmethod
    def _parts(data):
        candidates = data.get('candidates') or [{}]
        content = candidates[0].get('content') or {}
        return content.get('parts') or [], candidates[0].get('finishReason') or ''

    @staticmethod
    def _collect(parts, text, tool_calls, on_delta=None):
        for part in parts:
            if part.get('thought'):
                continue
            if 'text' in part:
                text.append(part['text'])
                if on_delta:
                    on_delta(part['text'])
            elif 'functionCall' in part:
                call = part['functionCall']
                tool_calls.append({
                    'id': call.get('id') or 'call_%s' % len(tool_calls),
                    'name': call.get('name') or '',
                    'arguments': call.get('args') or {},
                    'signature': part.get('thoughtSignature'),
                })

    def parse_chat(self, data, json_schema=None):
        if data.get('promptFeedback', {}).get('blockReason') and not data.get('candidates'):
            raise ValueError('Blocked: %s' % data['promptFeedback']['blockReason'])
        parts, finish_reason = self._parts(data)
        text, tool_calls = [], []
        self._collect(parts, text, tool_calls)
        usage = data.get('usageMetadata') or {}
        return self.finish(''.join(text), tool_calls,
                           _usage(usage.get('promptTokenCount'), usage.get('candidatesTokenCount')),
                           finish_reason, json_schema)

    def parse_stream(self, lines, on_delta=None, json_schema=None):
        text, tool_calls, usage, finish_reason = [], [], {}, ''
        for chunk in iter_sse(lines):
            if chunk.get('error'):
                raise ValueError(error_message(chunk))
            parts, reason = self._parts(chunk)
            self._collect(parts, text, tool_calls, on_delta)
            finish_reason = reason or finish_reason
            usage = chunk.get('usageMetadata') or usage
        return self.finish(''.join(text), tool_calls,
                           _usage(usage.get('promptTokenCount'), usage.get('candidatesTokenCount')),
                           finish_reason, json_schema)

    def models_request(self):
        return self.base_url + '/models?pageSize=1000'

    def parse_models(self, data):
        models = []
        for item in data.get('models') or []:
            name = item.get('name') or ''
            methods = item.get('supportedGenerationMethods') or []
            embeds = 'embedContent' in methods or 'batchEmbedContents' in methods
            chats = 'generateContent' in methods
            if not (embeds or chats):
                continue
            models.append({
                'model_id': name.removeprefix('models/'),
                'name': item.get('displayName') or name,
                'context_size': item.get('inputTokenLimit') or 0,
                'cap_chat': chats,
                'cap_embeddings': embeds,
                'cap_vision': chats,
                'cap_tools': chats,
                'cap_json': chats,
            })
        return models

    def embed_request(self, model, texts):
        path = self.model_path(model)
        return '%s/%s:batchEmbedContents' % (self.base_url, path), {'requests': [
            {'model': path, 'content': {'parts': [{'text': text}]}} for text in texts]}

    def parse_embed(self, data):
        return [row.get('values') for row in data.get('embeddings') or []], _usage(0, 0)


ADAPTERS = {
    'openai_compatible': OpenAIAdapter,
    'azure_openai': AzureOpenAIAdapter,
    'anthropic': AnthropicAdapter,
    'gemini': GeminiAdapter,
}


def get_adapter(config):
    return ADAPTERS[config['api_type']](config)
