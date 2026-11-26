{
    'name': 'MCP Client - Outside Tools for AI Agents',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Let the AI agents of Odoo use the tools of outside MCP servers: Streamable HTTP, bearer '
               'tokens or OAuth sign-in with PKCE, per tool on/off and read-only choice, allowed groups, usage log',
    'description': """
Connect Odoo to MCP servers outside Odoo. Their tools are imported as AI tools: the AI Assistant
in Discuss and the agents of the AI engine call them, read-only tools directly and the others after
the user confirms. Authentication with a bearer token or an OAuth sign-in (PKCE, token refresh),
allowed groups per server and every call in the AI usage log.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai'],
    'data': [
        'security/ir.access.csv',
        'views/om_ai_mcp_remote_views.xml',
        'views/om_ai_tool_views.xml',
        'views/om_ai_usage_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
