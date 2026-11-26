import re

from odoo import api, fields, models

class OmAiModel(models.Model):
    _name = 'om.ai.model'
    _description = 'AI Model'
    _order = 'provider_id, sequence, name'

    name = fields.Char(required=True)
    model_id = fields.Char(string='Model ID', required=True,
                           help='The model name the provider expects, e.g. gpt-4o-mini or a deployment name.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    provider_id = fields.Many2one('om.ai.provider', string='Provider', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='provider_id.company_id', store=True, index=True)
    api_type = fields.Selection(related='provider_id.api_type')
    cap_chat = fields.Boolean(string='Chat', default=True)
    cap_vision = fields.Boolean(string='Vision')
    cap_tools = fields.Boolean(string='Tools', default=True)
    cap_json = fields.Boolean(string='JSON Output', default=True)
    cap_embeddings = fields.Boolean(string='Embeddings')
    context_size = fields.Integer(string='Context Size', help='Maximum number of tokens the model reads.')
    input_price = fields.Float(string='Input Price', digits=(16, 4),
                               help='Price in USD per million prompt tokens, used for cost estimates.')
    output_price = fields.Float(string='Output Price', digits=(16, 4),
                                help='Price in USD per million completion tokens, used for cost estimates.')

    _model_provider_unique = models.Constraint('UNIQUE(provider_id, model_id)',
                                               'This model is already set on the provider.')

    @api.depends('name', 'provider_id')
    def _compute_display_name(self):
        for model in self:
            model.display_name = '%s / %s' % (model.provider_id.name, model.name) if model.provider_id else model.name

    @api.model
    def _guess_capabilities(self, model_id):
        """Capabilities guessed from the model name; edit them when wrong."""
        name = (model_id or '').lower()
        if re.search(r'embed|bge-|e5-|minilm|nomic', name):
            return {'cap_chat': False, 'cap_tools': False, 'cap_json': False, 'cap_embeddings': True}
        vision = bool(re.search(r'gpt-4o|gpt-4\.1|gpt-5|vision|claude|gemini|llava|pixtral|-vl|grok-4|llama-4|gemma-3|qwen.*vl', name))
        return {'cap_chat': True, 'cap_vision': vision, 'cap_tools': True, 'cap_json': True, 'cap_embeddings': False}

    def _supports(self, purpose):
        self.ensure_one()
        if purpose == 'embeddings':
            return self.cap_embeddings
        if purpose == 'vision':
            return self.cap_vision
        return self.cap_chat

    def _estimate_cost(self, prompt_tokens, completion_tokens):
        self.ensure_one()
        return (prompt_tokens * self.input_price + completion_tokens * self.output_price) / 1e6
