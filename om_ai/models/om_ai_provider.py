import json

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# preset: (label, api type, default base URL, needs a key)
PRESETS = {
    'openai': ('OpenAI', 'openai_compatible', 'https://api.openai.com/v1', True),
    'anthropic': ('Anthropic', 'anthropic', 'https://api.anthropic.com/v1', True),
    'gemini': ('Google Gemini', 'gemini', 'https://generativelanguage.googleapis.com/v1beta', True),
    'azure': ('Azure OpenAI', 'azure_openai', 'https://YOUR-RESOURCE.openai.azure.com/openai/v1', True),
    'mistral': ('Mistral', 'openai_compatible', 'https://api.mistral.ai/v1', True),
    'groq': ('Groq', 'openai_compatible', 'https://api.groq.com/openai/v1', True),
    'deepseek': ('DeepSeek', 'openai_compatible', 'https://api.deepseek.com/v1', True),
    'xai': ('xAI', 'openai_compatible', 'https://api.x.ai/v1', True),
    'openrouter': ('OpenRouter', 'openai_compatible', 'https://openrouter.ai/api/v1', True),
    'together': ('Together', 'openai_compatible', 'https://api.together.xyz/v1', True),
    'perplexity': ('Perplexity', 'openai_compatible', 'https://api.perplexity.ai', True),
    'ollama': ('Ollama (local)', 'openai_compatible', 'http://localhost:11434/v1', False),
    'lmstudio': ('LM Studio (local)', 'openai_compatible', 'http://localhost:1234/v1', False),
    'vllm': ('vLLM (local)', 'openai_compatible', 'http://localhost:8000/v1', False),
    'localai': ('LocalAI (local)', 'openai_compatible', 'http://localhost:8080/v1', False),
    'custom': ('Other OpenAI compatible', 'openai_compatible', '', False),
}


class OmAiProvider(models.Model):
    _name = 'om.ai.provider'
    _description = 'AI Provider'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company,
                                 help='Leave empty to share the provider with all companies.')
    preset = fields.Selection([(key, value[0]) for key, value in PRESETS.items()],
                              string='Provider', required=True, default='openai')
    api_type = fields.Selection([
        ('openai_compatible', 'OpenAI compatible API'),
        ('anthropic', 'Anthropic Messages API'),
        ('gemini', 'Gemini API'),
        ('azure_openai', 'Azure OpenAI'),
    ], string='API Type', required=True, default='openai_compatible')
    base_url = fields.Char(string='Base URL', required=True, default='https://api.openai.com/v1')
    api_version = fields.Char(string='API Version', help='Azure OpenAI deployment routes only, e.g. 2024-10-21. '
                                                          'Not used with a base URL ending in /openai/v1.')
    api_key = fields.Char(string='Stored API Key', groups='om_ai.group_ai_manager', copy=False)
    api_key_input = fields.Char(string='API Key', compute='_compute_api_key_input', inverse='_inverse_api_key_input',
                                groups='om_ai.group_ai_manager',
                                help='The key is kept on the server and never sent back to the browser. '
                                     'Type a new key to replace it.')
    api_key_set = fields.Boolean(string='Key Saved', compute='_compute_api_key_set')
    is_local = fields.Boolean(string='Local Model Server', compute='_compute_is_local')
    extra_headers = fields.Text(string='Extra Headers', help='JSON object of extra HTTP headers sent with each call, '
                                                             'e.g. {"HTTP-Referer": "https://example.com"}.')
    timeout = fields.Integer(string='Timeout (s)', default=60)
    max_retries = fields.Integer(string='Retries', default=2,
                                 help='Retries with a growing pause when the provider is busy (429) or fails (5xx).')
    model_ids = fields.One2many('om.ai.model', 'provider_id', string='Models')
    model_count = fields.Integer(compute='_compute_model_count')
    note = fields.Text()

    _timeout_positive = models.Constraint('CHECK(timeout > 0)', 'The timeout must be positive.')

    def _has_field_access(self, field, operation):
        # the stored key is only readable by server code running as superuser
        if field.name == 'api_key' and operation == 'read' and not self.env.su:
            return False
        return super()._has_field_access(field, operation)

    def _compute_api_key_input(self):
        self.api_key_input = False

    def _inverse_api_key_input(self):
        for provider in self:
            if provider.api_key_input:
                provider.sudo().api_key = provider.api_key_input.strip()

    def _compute_api_key_set(self):
        for provider in self:
            provider.api_key_set = bool(provider.sudo().api_key)

    @api.depends('preset')
    def _compute_is_local(self):
        for provider in self:
            provider.is_local = provider.preset in ('ollama', 'lmstudio', 'vllm', 'localai')

    @api.depends('model_ids')
    def _compute_model_count(self):
        for provider in self:
            provider.model_count = len(provider.model_ids)

    @api.onchange('preset')
    def _onchange_preset(self):
        label, api_type, url, _key = PRESETS.get(self.preset, PRESETS['custom'])
        self.api_type = api_type
        if url:
            self.base_url = url
        if not self.name or self.name in [value[0] for value in PRESETS.values()]:
            self.name = label

    @api.constrains('extra_headers')
    def _check_extra_headers(self):
        for provider in self:
            if provider.extra_headers:
                try:
                    headers = json.loads(provider.extra_headers)
                except ValueError:
                    headers = None
                if not isinstance(headers, dict):
                    raise ValidationError(self.env._('Extra Headers must be a JSON object, e.g. {"X-Title": "Odoo"}.'))

    def _get_config(self):
        """Connection settings read on the server, key included."""
        self.ensure_one()
        provider = self.sudo()
        headers = json.loads(provider.extra_headers) if provider.extra_headers else {}
        return {
            'api_type': provider.api_type,
            'preset': provider.preset,
            'base_url': provider.base_url,
            'api_key': provider.api_key or '',
            'api_version': provider.api_version,
            'extra_headers': {str(key): str(value) for key, value in headers.items()},
            'timeout': provider.timeout or 60,
            'max_retries': max(provider.max_retries, 0),
        }

    def action_test_connection(self):
        self.ensure_one()
        models_found = self.env['om.ai']._ai_list_models(self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': self.env._('Connection works'),
                'message': self.env._('%(provider)s answered with %(count)s models.',
                                      provider=self.name, count=len(models_found)),
            },
        }

    def action_fetch_models(self):
        self.ensure_one()
        found = self.env['om.ai']._ai_list_models(self)
        if not found:
            raise UserError(self.env._('The provider returned no models. Add them by hand on the Models tab.'))
        Model = self.env['om.ai.model'].with_context(active_test=False)
        existing = {model.model_id: model for model in Model.search([('provider_id', '=', self.id)])}
        created = updated = 0
        for vals in found:
            vals = dict(vals)
            model_id = vals['model_id']
            guessed = Model._guess_capabilities(model_id)
            for key, value in guessed.items():
                vals.setdefault(key, value)
            record = existing.get(model_id)
            if record:
                # keep prices and capabilities the user edited; refresh facts from the API
                update = {key: vals[key] for key in ('name', 'context_size') if vals.get(key)}
                for key in ('input_price', 'output_price'):
                    if vals.get(key) and not record[key]:
                        update[key] = vals[key]
                record.write(update)
                updated += 1
            else:
                Model.create(dict(vals, provider_id=self.id))
                created += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': self.env._('Models fetched'),
                'message': self.env._('%(created)s new, %(updated)s updated.', created=created, updated=updated),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_view_models(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('om_ai.om_ai_model_action')
        action['domain'] = [('provider_id', '=', self.id)]
        action['context'] = {'default_provider_id': self.id}
        return action
