{
    'name': 'Planning - Employees',
    'version': '20.0.1.0.0',
    'category': 'Services/Planning',
    'summary': 'Plan employees: working schedules, departments and managers in the planning, '
               'schedules emailed to employees, open shift claims and switches approved by their manager',
    'description': 'Bridge between Planning and Employees: every employee is a planning resource with its '
                   'working schedule, department and manager.',
    'author': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'support': 'odoomates@gmail.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'depends': ['om_planning', 'hr'],
    'data': [
        'views/hr_employee_views.xml',
        'views/hr_department_views.xml',
        'views/om_planning_slot_views.xml',
        'views/om_planning_request_views.xml',
    ],
    'demo': [
        'demo/om_planning_hr_demo.xml',
    ],
    'installable': True,
    'auto_install': True,
}
