# -*- coding: utf-8 -*-
###################################################################################
#    Odoo Mates
#    Copyright (C) 2019-TODAY Odoo Mates.
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
###################################################################################
{
    'name': 'Task Check List',
    'version': '13.0.1.0.0',
    'summary': """Checklist for Task Completion""",
    'description': """Evaluate task completion on the basis of checklists""",
    'category': 'Project',
    'author': 'Odoo Mates',
    'company': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'website': 'http://odoomates.tech',
    'depends': ['project'],
    'live_test_url': 'https://www.youtube.com/watch?v=bEhhlB2dNT0',
    'data': [
        'security/ir.model.access.csv',
        'views/project_task_view.xml',
        'views/task_checklist_view.xml',
    ],
    'demo': [
        'demo/checklist_demo.xml'
    ],
    'images': ['static/description/banner.jpg'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
