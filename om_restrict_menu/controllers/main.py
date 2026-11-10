# -*- coding: utf-8 -*-
from odoo import http

from odoo.addons.web.controllers.main import Home

if hasattr(Home, 'web_load_menus'):

    class HideMenuHome(Home):

        @http.route()
        def web_load_menus(self, unique):
            response = super(HideMenuHome, self).web_load_menus(unique)
            response.headers['Cache-Control'] = 'no-store'
            return response
