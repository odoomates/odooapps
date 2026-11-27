{
    'name': 'Documents - Project',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Documents',
    'summary': 'A folder per project with the files of its tasks, shared with the customer of the project',
    'description': 'Each project gets its folder in Documents, the files attached to the project and its tasks '
                   'land in it, and the folder is shared with the customer of the project in one click.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_documents', 'project'],
    'data': [
        'data/om_documents_project_data.xml',
        'views/project_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
