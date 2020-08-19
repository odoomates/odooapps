###################################################################################
#
#    Copyright (C) 2019 Odoo Mates
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###################################################################################

{
    'name': 'Project-Task Search Panel',
    'summary': 'Kanban Search Panel for Project & Task',
    'version': '12.0.1.0.0',
    'category': 'Extra Tools',
    'license': 'AGPL-3',
    'author': 'Odoo Mates',
    'company': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'website': 'http://odoomates.tech',
    'support': 'odoomates@gmail.com',
    'depends': ['muk_web_searchpanel', 'project'],
    'data': ["views/view.xml"],
    'images': ['static/description/banner.png'],
    'application': False,
    'installable': True,
    'auto_install': False,
}
