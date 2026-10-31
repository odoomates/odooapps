{
    'name': 'File Layouts',
    'version': '1.0.0',
    'category': 'Productivity',
    'summary': 'Design the CSV, fixed width or Excel files you send out of Odoo and export them from the Action '
               'menu',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/om_file_layout_security.xml',
        'security/ir.access.csv',
        'views/om_file_layout_views.xml',
        'views/menu.xml',
    ],
    'demo': ['demo/om_file_layout_demo.xml'],
    'images': ['static/description/banner.gif'],
}
