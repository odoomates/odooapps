from odoo.exceptions import AccessError
from odoo.http import request, route

from odoo.addons.html_editor.controllers.main import HTML_Editor


class OmAiHtmlEditor(HTML_Editor):

    @route()
    def generate_text(self, prompt, conversation_history):
        """Same contract as the standard route: answer text or a UserError.
        Uses the company's own AI provider when the setting is on."""
        if not request.env.company.sudo().om_ai_editor_provider:
            return super().generate_text(prompt, conversation_history)
        if not request.env.user._is_internal():
            raise AccessError(request.env._("Only internal users can use AI text generation."))
        messages = []
        for item in conversation_history or []:
            if isinstance(item, dict) and item.get('role') in ('system', 'user', 'assistant') and item.get('content'):
                messages.append({'role': item['role'], 'content': str(item['content'])})
        if not any(message['role'] == 'system' for message in messages):
            template = request.env['om.ai.prompt'].sudo().search([('code', '=', 'html_editor')], limit=1)
            messages = [m for m in template._render() if m['role'] == 'system'] + messages
        messages.append({'role': 'user', 'content': str(prompt or '')})
        result = request.env['om.ai']._ai_chat(messages, purpose='chat', feature='html_editor')
        return result['text']
