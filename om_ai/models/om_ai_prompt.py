import re

from odoo import fields, models
from odoo.exceptions import UserError

PLACEHOLDER = re.compile(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}')


class OmAiPrompt(models.Model):
    _name = 'om.ai.prompt'
    _description = 'AI Prompt Template'
    _order = 'feature, sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(help='Technical name features use to find the template.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    feature = fields.Char(help='Feature that uses this template, e.g. discuss or html_editor.')
    company_id = fields.Many2one('res.company', string='Company')
    purpose = fields.Selection([
        ('chat', 'Chat'),
        ('fast', 'Fast'),
        ('vision', 'Vision'),
    ], default='chat', required=True)
    system_prompt = fields.Text(string='System Prompt', translate=True)
    user_template = fields.Text(string='User Message', translate=True,
                                help='Text with placeholders such as {{ customer }} that features fill in.')
    placeholders = fields.Char(compute='_compute_placeholders')

    _code_unique = models.Constraint('UNIQUE(code, company_id)', 'A template with this code already exists.')

    def _compute_placeholders(self):
        for prompt in self:
            names = PLACEHOLDER.findall('%s\n%s' % (prompt.system_prompt or '', prompt.user_template or ''))
            prompt.placeholders = ', '.join(dict.fromkeys(names))

    @staticmethod
    def _render_text(template, values):
        """Replace {{ name }} by values[name]; nothing in the text is evaluated."""
        values = values or {}

        def replace(match):
            value = values.get(match.group(1), '')
            return '' if value is None or value is False else str(value)
        return PLACEHOLDER.sub(replace, template or '')

    def _render(self, values=None):
        """Return the messages of this template filled with ``values``."""
        self.ensure_one()
        messages = []
        if self.system_prompt:
            messages.append({'role': 'system', 'content': self._render_text(self.system_prompt, values)})
        if self.user_template:
            messages.append({'role': 'user', 'content': self._render_text(self.user_template, values)})
        return messages

    def _get_by_code(self, code):
        prompt = self.search([('code', '=', code), ('company_id', 'in', [self.env.company.id, False])],
                             order='company_id', limit=1)
        if not prompt:
            raise UserError(self.env._('The AI prompt template "%s" is missing.', code))
        return prompt
