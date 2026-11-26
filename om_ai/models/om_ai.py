import base64
import json
import logging
import re
import time

import requests

from odoo import api, models
from odoo.exceptions import AccessError, UserError

from .ai_adapters import error_message, get_adapter

_logger = logging.getLogger(__name__)

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504, 529}
MAX_LOG_TEXT = 20000


class OmAi(models.AbstractModel):
    """The AI engine. Features call it, never a provider directly:

        result = self.env['om.ai']._ai_chat(
            [{'role': 'user', 'content': 'Write a short thank you note.'}],
            purpose='fast', feature='my_feature')
        result['text']

    The result is a dict: text, tool_calls, json, usage, model, model_id,
    provider, finish_reason.
    """
    _name = 'om.ai'
    _description = 'AI Engine'

    # ------------------------------------------------------------------
    # Model selection, access and limits
    # ------------------------------------------------------------------
    @api.model
    def _ai_check_access(self):
        if not self.env.su and not self.env.user.has_group('om_ai.group_ai_user'):
            raise AccessError(self.env._('You are not allowed to use the AI features. Ask your administrator '
                                         'for the AI / User access.'))

    @api.model
    def _ai_get_model(self, purpose='chat', model=None):
        """Return the om.ai.model to use: the one given, else the company default for the purpose."""
        Model = self.env['om.ai.model'].sudo()
        if model:
            if isinstance(model, models.BaseModel):
                record = model.sudo()
            elif isinstance(model, int):
                record = Model.browse(model).exists()
            else:
                record = Model.search([('model_id', '=', model), ('company_id', 'in', [self.env.company.id, False])],
                                      limit=1)
            if not record:
                raise UserError(self.env._('The AI model "%s" is not set up.', model))
            return record
        company = self.env.company.sudo()
        chain = {
            'chat': ['chat'],
            'fast': ['fast', 'chat'],
            'vision': ['vision', 'chat'],
            'embeddings': ['embeddings'],
        }.get(purpose, ['chat'])
        for key in chain:
            record = company['om_ai_%s_model_id' % key]
            if record and record.active and record.provider_id.active:
                return record
        labels = {
            'chat': self.env._('Chat'), 'fast': self.env._('Fast'),
            'vision': self.env._('Vision'), 'embeddings': self.env._('Embeddings'),
        }
        raise UserError(self.env._('No AI model is set for "%(purpose)s". An administrator can set one in '
                                   'Settings > General Settings > AI.', purpose=labels.get(purpose, purpose)))

    @api.model
    def _ai_check_limits(self, feature=None):
        company = self.env.company.sudo()
        Usage = self.env['om.ai.usage']
        checks = []
        if company.om_ai_user_daily_tokens or company.om_ai_user_daily_cost:
            tokens, cost = Usage._get_daily_totals(user=self.env.user, company=company)
            checks.append((tokens, cost, company.om_ai_user_daily_tokens, company.om_ai_user_daily_cost,
                           self.env._('your daily AI limit')))
        if company.om_ai_company_daily_tokens or company.om_ai_company_daily_cost:
            tokens, cost = Usage._get_daily_totals(company=company)
            checks.append((tokens, cost, company.om_ai_company_daily_tokens, company.om_ai_company_daily_cost,
                           self.env._('the daily AI limit of %s', company.name)))
        for tokens, cost, max_tokens, max_cost, label in checks:
            if (max_tokens and tokens >= max_tokens) or (max_cost and cost >= max_cost):
                message = self.env._('You have reached %(limit)s (%(tokens)s tokens, %(cost)s USD used today). '
                                     'Try again tomorrow or ask your administrator to raise the limit.',
                                     limit=label, tokens=tokens, cost=round(cost, 4))
                self._ai_log({'feature': feature, 'status': 'blocked', 'error': message}, separate=True)
                raise UserError(message)

    # ------------------------------------------------------------------
    # Usage log
    # ------------------------------------------------------------------
    @api.model
    def _ai_log(self, vals, separate=False):
        vals = dict(vals, user_id=self.env.user.id, company_id=self.env.company.id)
        if separate:
            # errors are kept even when the caller's transaction is rolled back
            try:
                with self.env.registry.cursor() as cr:
                    self.env(cr=cr, su=True)['om.ai.usage'].create(vals)
            except Exception:  # noqa: BLE001
                _logger.exception('Could not log AI usage')
        else:
            self.env['om.ai.usage'].sudo().create(vals)

    @staticmethod
    def _ai_log_text(value):
        def strip_images(item):
            if isinstance(item, dict):
                return {key: ('<%s image(s)>' % len(val) if key == 'images' else strip_images(val))
                        for key, val in item.items()}
            if isinstance(item, list):
                return [strip_images(val) for val in item]
            return item
        if not isinstance(value, str):
            value = json.dumps(strip_images(value), ensure_ascii=False, indent=1, default=str)
        return value[:MAX_LOG_TEXT]

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    @api.model
    def _ai_http(self, provider, adapter, url, payload=None, stream=False, method='POST'):
        """Send one request with retries on busy/failing providers. Return the response."""
        config = provider._get_config()
        attempts = config['max_retries'] + 1
        for attempt in range(attempts):
            last = attempt == attempts - 1
            try:
                response = requests.request(method, url, json=payload, headers=adapter.headers(),
                                            timeout=config['timeout'], stream=stream)
            except requests.exceptions.Timeout:
                if last:
                    raise UserError(self.env._('%(provider)s did not answer within %(timeout)s seconds.',
                                               provider=provider.name, timeout=config['timeout'])) from None
                self._ai_sleep(attempt)
                continue
            except requests.exceptions.RequestException as error:
                if last:
                    raise UserError(self.env._('Could not reach %(provider)s at %(url)s: %(error)s',
                                               provider=provider.name, url=config['base_url'],
                                               error=error.__class__.__name__)) from None
                self._ai_sleep(attempt)
                continue
            if response.status_code < 400:
                return response
            if response.status_code in RETRY_STATUS and not last:
                self._ai_sleep(attempt, response.headers.get('Retry-After'))
                continue
            try:
                body = response.json()
            except ValueError:
                body = None
            message = error_message(body, (response.text or '')[:500] or response.reason)
            raise UserError(self.env._('%(provider)s returned an error (%(status)s): %(message)s',
                                       provider=provider.name, status=response.status_code, message=message))
        raise UserError(self.env._('%s could not be reached.', provider.name))

    @staticmethod
    def _ai_sleep(attempt, retry_after=None):
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            delay = 2 ** attempt
        time.sleep(max(0.2, min(delay, 20)))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @api.model
    def _ai_normalise_messages(self, messages, images=None):
        if isinstance(messages, str):
            messages = [{'role': 'user', 'content': messages}]
        result = [dict(message) for message in messages or []]
        if images:
            parsed = [self._ai_image(image) for image in images]
            for message in reversed(result):
                if message.get('role') == 'user':
                    message['images'] = (message.get('images') or []) + parsed
                    break
            else:
                result.append({'role': 'user', 'content': '', 'images': parsed})
        if not result:
            raise UserError(self.env._('Nothing to send to the AI.'))
        return result

    @staticmethod
    def _ai_image(image):
        """Accept {'mime_type', 'data'}, a data URL, base64 text or raw bytes."""
        if isinstance(image, dict):
            return {'mime_type': image.get('mime_type') or 'image/png', 'data': image['data']}
        if isinstance(image, bytes):
            return {'mime_type': 'image/png', 'data': base64.b64encode(image).decode()}
        match = re.match(r'data:([\w/+.-]+);base64,(.*)', image or '', re.S)
        if match:
            return {'mime_type': match.group(1), 'data': match.group(2)}
        return {'mime_type': 'image/png', 'data': image}

    @api.model
    def _ai_chat(self, messages, purpose='chat', model=None, tools=None, json_schema=None, images=None,
                 stream=False, feature=None, max_tokens=None, temperature=None, on_delta=None):
        """Send a conversation to the AI and return the normalised answer.

        :param messages: list of {'role', 'content'} dicts (or one user text)
        :param purpose: chat, fast, vision or embeddings: picks the company default model
        :param model: om.ai.model record, id or model id to force a model
        :param tools: om.ai.tool records or a list of {'name', 'description', 'parameters'}
        :param json_schema: JSON schema the answer must follow; the parsed value is in result['json']
        :param images: images added to the last user message
        :param stream: stream the answer; ``on_delta(text)`` is called for each piece
        :param feature: name of the calling feature, for the usage log
        :return: dict text, tool_calls, json, usage, model, model_id, provider, finish_reason
        """
        self._ai_check_access()
        if images and purpose == 'chat':
            purpose = 'vision'
        ai_model = self._ai_get_model(purpose, model)
        provider = ai_model.provider_id
        self._ai_check_limits(feature)
        messages = self._ai_normalise_messages(messages, images)
        if isinstance(tools, models.BaseModel):
            tools = tools._to_spec()
        adapter = get_adapter(provider._get_config())
        url, payload = adapter.chat_request(ai_model.model_id, messages, tools=tools or None,
                                            json_schema=json_schema, max_tokens=max_tokens,
                                            temperature=temperature, stream=stream)
        company = self.env.company.sudo()
        log = {
            'feature': feature,
            'provider_id': provider.id,
            'model_id': ai_model.id,
            'model_name': ai_model.model_id,
        }
        if company.om_ai_log_content:
            log['request_text'] = self._ai_log_text({'messages': messages, 'tools': [t['name'] for t in tools or []]})
        started = time.monotonic()
        try:
            response = self._ai_http(provider, adapter, url, payload, stream=stream)
            try:
                if stream:
                    result = adapter.parse_stream(response.iter_lines(), on_delta=on_delta, json_schema=json_schema)
                else:
                    result = adapter.parse_chat(response.json(), json_schema=json_schema)
            except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
                raise UserError(self.env._('%(provider)s sent an answer that could not be read: %(error)s',
                                           provider=provider.name, error=error)) from None
            finally:
                response.close()
        except UserError as error:
            log.update(status='error', error=str(error.args[0]), duration=time.monotonic() - started)
            self._ai_log(log, separate=True)
            raise
        usage = result['usage']
        log.update(
            prompt_tokens=usage['prompt_tokens'],
            completion_tokens=usage['completion_tokens'],
            total_tokens=usage['total_tokens'],
            cost=ai_model._estimate_cost(usage['prompt_tokens'], usage['completion_tokens']),
            duration=time.monotonic() - started,
        )
        if company.om_ai_log_content:
            log['response_text'] = self._ai_log_text(
                result['text'] or {'tool_calls': result['tool_calls']})
        self._ai_log(log)
        result.update(model=ai_model.model_id, model_id=ai_model.id, provider=provider.name)
        return result

    @api.model
    def _ai_embed(self, texts, model=None, feature=None):
        """Return one embedding vector (list of floats) per text."""
        self._ai_check_access()
        single = isinstance(texts, str)
        texts = [texts] if single else list(texts)
        ai_model = self._ai_get_model('embeddings', model)
        provider = ai_model.provider_id
        if provider.api_type == 'anthropic':
            raise UserError(self.env._('%s has no embeddings API. Set an embeddings model of another provider.',
                                       provider.name))
        self._ai_check_limits(feature)
        adapter = get_adapter(provider._get_config())
        url, payload = adapter.embed_request(ai_model.model_id, texts)
        log = {'feature': feature or 'embeddings', 'provider_id': provider.id, 'model_id': ai_model.id,
               'model_name': ai_model.model_id}
        started = time.monotonic()
        try:
            response = self._ai_http(provider, adapter, url, payload)
            try:
                vectors, usage = adapter.parse_embed(response.json())
            except (ValueError, KeyError, TypeError) as error:
                raise UserError(self.env._('%(provider)s sent an answer that could not be read: %(error)s',
                                           provider=provider.name, error=error)) from None
        except UserError as error:
            log.update(status='error', error=str(error.args[0]), duration=time.monotonic() - started)
            self._ai_log(log, separate=True)
            raise
        log.update(prompt_tokens=usage['prompt_tokens'], total_tokens=usage['total_tokens'],
                   cost=ai_model._estimate_cost(usage['prompt_tokens'], 0), duration=time.monotonic() - started)
        self._ai_log(log)
        return vectors[0] if single else vectors

    @api.model
    def _ai_list_models(self, provider):
        """Ask the provider for its models; return a list of om.ai.model values."""
        if not self.env.user.has_group('om_ai.group_ai_manager'):
            raise AccessError(self.env._('Only AI administrators can query providers.'))
        adapter = get_adapter(provider._get_config())
        response = self._ai_http(provider, adapter, adapter.models_request(), method='GET')
        try:
            return adapter.parse_models(response.json())
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise UserError(self.env._('%(provider)s sent a model list that could not be read: %(error)s',
                                       provider=provider.name, error=error)) from None

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------
    @api.model
    def _ai_run_agent(self, messages, tools=None, user=None, max_steps=6, purpose='chat', feature=None,
                      model=None, max_tokens=None, temperature=None):
        """Let the AI call tools until it answers.

        Tools run as ``user`` (default: the current user), never as superuser,
        so access rights and record rules apply. Read-only tools run directly;
        the others are returned in ``pending_actions`` for the user to confirm
        with :meth:`_ai_confirm_action`.

        :return: dict text, messages (the whole conversation), pending_actions,
                 steps, usage
        """
        engine = self.with_user(user or self.env.user)
        Tool = engine.env['om.ai.tool']
        if tools is None:
            tools = Tool._get_available(read_only=True)
        elif not isinstance(tools, models.BaseModel):
            tools = Tool._get_available(codes=tools)
        tools = tools.with_env(engine.env)
        by_code = {tool.code: tool for tool in tools.sudo()}
        spec = tools._to_spec()
        conversation = engine._ai_normalise_messages(messages)
        usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
        pending, steps, result = [], 0, {'text': ''}
        while True:
            last_step = steps >= max_steps
            result = engine._ai_chat(conversation, purpose=purpose, model=model,
                                     tools=None if last_step else spec, feature=feature,
                                     max_tokens=max_tokens, temperature=temperature)
            for key in usage:
                usage[key] += result['usage'][key]
            steps += 1
            if not result['tool_calls'] or last_step:
                conversation.append({'role': 'assistant', 'content': result['text']})
                break
            conversation.append({'role': 'assistant', 'content': result['text'], 'tool_calls': result['tool_calls']})
            for call in result['tool_calls']:
                tool = by_code.get(call['name'])
                if not tool:
                    output = {'error': 'Unknown tool %s.' % call['name']}
                elif tool.read_only:
                    output = tool.with_env(engine.env)._execute(call['arguments'])
                else:
                    pending.append({'tool': tool.code, 'tool_name': tool.name, 'arguments': call['arguments'],
                                    'tool_call_id': call['id']})
                    output = {'status': 'waiting for the user to confirm'}
                conversation.append({
                    'role': 'tool',
                    'tool_call_id': call['id'],
                    'name': call['name'],
                    'content': json.dumps(output, ensure_ascii=False, default=str)[:MAX_LOG_TEXT],
                })
            if pending:
                break
        return {
            'text': result.get('text') or '',
            'messages': conversation,
            'pending_actions': pending,
            'steps': steps,
            'usage': usage,
        }

    @api.model
    def _ai_confirm_action(self, action):
        """Run a pending action of :meth:`_ai_run_agent` once the user confirmed it."""
        self._ai_check_access()
        tool = self.env['om.ai.tool']._get_available(codes=[action['tool']])
        if not tool:
            raise AccessError(self.env._('You may not use the AI tool %s.', action['tool']))
        return tool._execute(action.get('arguments') or {})
