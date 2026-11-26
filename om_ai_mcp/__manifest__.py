{
    'name': 'MCP Server - Odoo for AI Apps',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'MCP server for Odoo: connect Claude.ai, Claude Desktop, Claude Code, Cursor, VS Code and other MCP '
               'clients to Odoo with OAuth 2.1 sign-in or a user API key, resources and prompts, read-only access, '
               'model permissions, rate limits and an audit log',
    'description': """
A Model Context Protocol (MCP) server inside Odoo. AI apps that speak MCP sign in with OAuth 2.1
(read only unless the user allows changes) or an MCP key and call the tools of the AI engine:
search, read, count and aggregate records, create, update and delete them, post in the chatter,
read and attach files, and run server actions. They also read records, printed reports and files
as resources and use prompt templates, always with the rights of the user.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/om_ai_mcp_data.xml',
        'views/om_mcp_model_access_views.xml',
        'views/om_mcp_oauth_views.xml',
        'views/oauth_templates.xml',
        'views/om_ai_prompt_views.xml',
        'views/om_mcp_log_views.xml',
        'views/om_mcp_session_views.xml',
        'views/om_mcp_key_views.xml',
        'views/om_mcp_connect_views.xml',
        'views/om_ai_tool_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/om_ai_mcp_demo.xml',
    ],
    'installable': True,
    'application': False,
}
