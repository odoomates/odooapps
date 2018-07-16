# -*- coding: utf-8 -*-

{
    'name': 'Task Check List',
    'version': '11.0.1.0.0',
    'summary': """Checklist for Task Completion""",
    'description': """Evaluate task completion on the basis of checklists""",
    'category': 'Project',
    'author': 'Odoo Mates',
    'company': 'Odoo Mates',
    'website': "",
    'depends': ['project'],
    'data': [
        'views/project_task_view.xml',
        'views/task_checklist_view.xml',
    ],
    'demo': [
        'demo/checklist_demo.xml'
    ],
    'images': [],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}

