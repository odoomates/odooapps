from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """Tell the browser which colour scheme it is looking at.

        The systray switch needs it to know which way round it is pointing.
        """
        info = super().session_info()
        info['om_color_scheme'] = self.color_scheme()
        user = self.env.user
        if user and not user._is_public():
            # the stored choice, which may be "system" where om_color_scheme is the
            # light or dark it resolved to
            info['om_color_scheme_pref'] = user.om_color_scheme or 'light'
            info['om_app_order'] = user.om_app_order or []
            info['om_sidebar_type'] = user.om_sidebar_type or 'none'
            info['om_chatter_position'] = user.om_chatter_position or 'auto'
            info['om_dialog_size'] = user.om_dialog_size or 'normal'
            company = self.env.company
            if company.om_home_background:
                info['om_home_background'] = '/om_theme_lite/company/%s/om_home_background?unique=%s' % (
                    company.id, company.write_date.timestamp() if company.write_date else 0)
        return info

    def color_scheme(self):
        """Pick the light or the dark asset bundle for this user.

        Community hardcodes this to "light" - the dark bundle exists but nothing
        ever asks for it. Reading the user's own preference is what turns it on.
        """
        scheme = self._om_color_scheme()
        if request:
            # web/static/src/views/view.js reads this cookie to colour graph and
            # pivot views, so it has to agree with the bundle we just chose
            request.future_response.set_cookie('color_scheme', scheme)
        return scheme

    def _om_color_scheme(self):
        user = self.env.user
        if not user or user._is_public():
            return 'light'
        scheme = user.om_color_scheme or 'light'
        if scheme == 'system':
            # The server cannot see the device setting. The browser reports it in
            # this cookie on every page (static/src/theme/device_scheme.js); until it
            # has, the page is served light.
            device = request.cookies.get('om_device_scheme') if request else None
            return 'dark' if device == 'dark' else 'light'
        return scheme
