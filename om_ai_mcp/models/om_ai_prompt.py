import re

from odoo import fields, models

from odoo.addons.om_ai.models.om_ai_prompt import PLACEHOLDER

NAME_CHARS = re.compile(r'[^a-zA-Z0-9_.-]+')


class OmAiPrompt(models.Model):
    _inherit = 'om.ai.prompt'

    mcp_available = fields.Boolean(string='Available to MCP',
                                   help='Offer this template to AI apps connected through the MCP server. The apps '
                                        'show it as a prompt (often a slash command) and ask for the placeholders.')
    mcp_description = fields.Char(string='MCP Description', translate=True,
                                  help='What the prompt does, shown in the AI app.')

    def _mcp_name(self):
        self.ensure_one()
        return NAME_CHARS.sub('_', self.code or '').strip('_') or 'prompt_%s' % self.id

    def _mcp_arguments(self):
        self.ensure_one()
        text = '%s\n%s' % (self.system_prompt or '', self.user_template or '')
        return list(dict.fromkeys(PLACEHOLDER.findall(text)))
