from odoo.tests import HttpCase, tagged

from odoo.addons.web.tests.test_js import qunit_error_checker


@tagged('post_install', '-at_install')
class TestOmWhatsappDeviceUi(HttpCase):
    """ The link window, in the browser: its QUnit tests. """

    def test_link_dialog(self):
        self.browser_js('/web/tests?mod=web&filter=om_whatsapp_device', "", "", login='admin', timeout=600,
                        error_checker=qunit_error_checker)
