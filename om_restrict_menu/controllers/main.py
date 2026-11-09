<<<<<<< HEAD
# The menus are fetched from /web/webclient/load_menus/<hash>, which the browser keeps for a year. They
# change with the current company: the browser asks the server every time, as it does from Odoo 19.
=======
# -*- coding: utf-8 -*-
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
from odoo import http

from odoo.addons.web.controllers.main import Home

<<<<<<< HEAD

class HideMenuHome(Home):

    @http.route()
    def web_load_menus(self, unique):
        response = super().web_load_menus(unique)
        response.headers['Cache-Control'] = 'no-store'
        return response
=======
if hasattr(Home, 'web_load_menus'):

    class HideMenuHome(Home):

        @http.route()
        def web_load_menus(self, unique):
            response = super(HideMenuHome, self).web_load_menus(unique)
            response.headers['Cache-Control'] = 'no-store'
            return response
>>>>>>> 07a27e2 ([ADD] om_restrict_menu: backport of 15.0)
