{
    'name': 'Field Service - Stock',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'summary': 'Parts used on field service jobs: a van stock location per technician, parts with lots and '
               'serial numbers taken from the van or the warehouse, stock moves to the customer when the job '
               'is done, equipment installed at the customer site, van replenishment',
    'description': 'Bridge between Field Service and Inventory: the technician records the parts used on the '
                   'job, the stock leaves their van when the job is done and the serial numbers installed are '
                   'kept on the customer.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_field_service', 'stock'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'wizard/om_fs_van_replenish_views.xml',
        'views/om_fs_equipment_views.xml',
        'views/project_task_views.xml',
        'views/hr_employee_views.xml',
        'views/res_partner_views.xml',
        'views/om_field_service_stock_menus.xml',
        'report/om_field_service_report.xml',
    ],
    'demo': [
        'demo/om_field_service_stock_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'om_field_service_stock/static/src/**/*',
        ],
    },
    'installable': True,
    'auto_install': True,
}
