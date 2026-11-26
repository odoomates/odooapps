{
    'name': 'AI Engine - Your Own AI Providers',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'AI engine for Odoo with your own provider or a local model: OpenAI compatible APIs, '
               'Claude, Gemini, Azure OpenAI, Mistral, Groq, DeepSeek, OpenRouter, Ollama, LM Studio, '
               'tool calling, usage log, daily limits, prompt templates, AI chat in Discuss',
    'description': """
One AI engine for Odoo: connect your own AI provider with your own key, or run a local model.
Providers and models with prices, defaults per purpose, a Python API with tool calling and
JSON output, a usage log with cost estimates and daily limits, prompt templates, an AI chat in
Discuss that looks up records you can see, and the editor text generation through your provider.
""",
    'sequence': 10,
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['mail', 'html_editor'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/om_ai_data.xml',
        'data/om_ai_tool_data.xml',
        'data/om_ai_prompt_data.xml',
        'views/om_ai_provider_views.xml',
        'views/om_ai_model_views.xml',
        'views/om_ai_prompt_views.xml',
        'views/om_ai_tool_views.xml',
        'views/om_ai_usage_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/om_ai_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_ai/static/src/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': True,
}
