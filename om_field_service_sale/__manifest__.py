{
    'name': 'Field Service - Sales',
    'version': '20.0.1.0.0',
    'category': 'Services/Field Service',
    'summary': 'Time and material for field service jobs: a sales order per job with the hours of the '
               'timesheets and the parts used, invoiced from the order; jobs covered by a warranty or a '
               'contract not charged; quotations for follow-up work from the job',
    'description': 'Bridge between Field Service and Sales: the travel and work time of the technicians and the '
                   'parts they use go to the sales order of the job, invoiced like any order.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_field_service_stock', 'sale_timesheet', 'sale_stock'],
    'data': [
        'data/om_field_service_sale_data.xml',
        'views/om_fs_job_type_views.xml',
        'views/project_task_views.xml',
        'views/sale_order_views.xml',
    ],
    'demo': [
        'demo/om_field_service_sale_demo.xml',
    ],
    'installable': True,
    'auto_install': True,
}
