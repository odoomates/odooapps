{
    'name': 'Planning - Maintenance',
    'version': '20.0.1.0.0',
    'category': 'Services/Planning',
    'summary': 'Plan maintenance equipment and technicians: every equipment is a planning resource, '
               'scheduled maintenance requests book the equipment and the technicians, equipment '
               'schedule on the Gantt, conflicts when the equipment is booked elsewhere',
    'description': 'Bridge between Planning and Maintenance: equipment becomes a planning resource, so a '
                   'machine under maintenance is busy for rentals, field service and any other planning.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_planning', 'maintenance'],
    'data': [
        'data/om_planning_maintenance_data.xml',
        'views/om_planning_slot_views.xml',
        'views/maintenance_equipment_views.xml',
        'views/maintenance_request_views.xml',
        'views/resource_resource_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'demo': [
        'demo/om_planning_maintenance_demo.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'auto_install': True,
}
