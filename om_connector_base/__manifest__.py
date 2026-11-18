{
    'name': 'Connector Base',
    'version': '1.1',
    'author': 'Odoo Mates',
    'category': 'Sales',
    'summary': 'Job queue, retries, external ID mappings and webhook helpers for shop and marketplace connectors',
    'description': 'The common engine of the Odoo Mates connectors (Shopify and others): a job queue with retries, '
                   'workflows for the imported orders (confirm, invoice, pay), mappings between external records and Odoo records, and webhook helpers.',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'depends': ['mail', 'sale_management', 'sale_stock'],
    'data': [
        'security/om_connector_groups.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/om_connector_job_views.xml',
        'views/om_connector_order_workflow_views.xml',
        'views/menu.xml',
    ],
    'images': ['static/description/banner.gif'],
}
