{
    'name': 'AI Fields - Fill Fields with Your Own AI',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'AI fields on any model: a prompt with record values fills a text, selection, many2one, boolean or '
               'number field on demand, when other fields change or on a schedule, and a server action '
               '"Update Fields with AI" for automation rules, with your own AI provider or a local model',
    'description': """
AI fields for Odoo on the AI engine. An administrator picks a field of any model, or creates one, and writes a
prompt with record values such as {{ partner_id.name }}. The AI fills the field on demand from the Actions menu,
in the background when chosen fields change, or on a schedule for empty values. Selection and many2one fields only
take valid values. A server action type "Update Fields with AI" fills several fields at once in automation rules.
""",
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_ai', 'base_automation'],
    'data': [
        'security/ir.access.csv',
        'data/om_ai_fields_data.xml',
        'views/om_ai_field_views.xml',
        'views/om_ai_field_job_views.xml',
        'views/ir_actions_server_views.xml',
        'views/menus.xml',
    ],
    'demo': [
        'demo/om_ai_fields_demo.xml',
    ],
    'installable': True,
    'application': False,
}
