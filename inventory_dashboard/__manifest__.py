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
    'name': "Inventory Dashboard",
    'version': '12.0.1.0.0',
    'summary': """Inventory dashboard""",
    'description': """""",
    'author': 'Odoo Mates',
    'company': 'Odoo Mates',
    'maintainer': 'Odoo Mates',
    'category': 'Warehouse',
    'depends': ['stock'],
    'data': [
        'views/stock_picking.xml',
    ],
    'demo': [],
    'images': ['static/description/banner.jpg'],
}
