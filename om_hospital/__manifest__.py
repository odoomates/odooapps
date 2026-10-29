{
    'name': 'Odoo 18 Development Tutorials',
    'version': '18.0.3.0.0',
    'summary': 'Learn Odoo 18 development: eLearning courses with the Odoo Mates videos, and a hospital app to build',
    'description': """
Learn Odoo 18 development inside your own Odoo: six eLearning courses with the
videos of Odoo Mates, notes on what changed in Odoo 18, quizzes, and om_hospital,
the hospital app the lessons build.
""",
    'category': 'Tutorials',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'AGPL-3',
    'depends': ['mail', 'sale', 'website_slides'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/wizard_views.xml',
        'views/patient_views.xml',
        'views/doctor_views.xml',
        'views/appointment_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'report/patient_card.xml',
        'data/slide_channel_data.xml',
    ],
    'images': ['static/description/banner.png'],
    'application': True,
    'sequence': -100,
}
