{
    'name': 'Planning - Fleet',
    'version': '20.0.1.0.0',
    'category': 'Services/Planning',
    'summary': 'Plan vehicles: every vehicle is a planning resource, a vehicle with a driver follows the '
               'slots of the driver, vehicle bookings and conflicts, vehicle schedule on the Gantt',
    'description': 'Bridge between Planning and Fleet: vehicles become planning resources, booked on their '
                   'own or with the people who drive them.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_planning', 'fleet'],
    'data': [
        'views/om_planning_slot_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/resource_resource_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [
        'demo/om_planning_fleet_demo.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': True,
}
