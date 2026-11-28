{
    'name': 'Rental - Planning',
    'version': '20.0.1.0.1',
    'category': 'Sales/Sales',
    'summary': 'Rent identified units from the planning: availability by units (equipment, vehicles, '
               'rooms), unit booked from pickup to return with preparation time, next free date, '
               'late returns that clash with the next booking, unit schedule on the Gantt, delivery crew',
    'description': 'Rental products can be rented by units: each unit is a planning resource, so a unit in '
                   'maintenance, on a field service job or on another rental is not offered twice.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_sale_renting', 'om_planning_maintenance'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'views/product_views.xml',
        'views/om_planning_slot_views.xml',
        'views/sale_order_views.xml',
        'views/resource_resource_views.xml',
    ],
    'demo': [
        'demo/rental_planning_demo.xml',
    ],
    'installable': True,
}
