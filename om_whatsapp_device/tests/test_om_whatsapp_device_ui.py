from odoo import Command
from odoo.tests import HttpCase, tagged

from .fake_bridge import fake_bridge

WAIT_FOR = """
const waitFor = async (selector, text) => {
    for (let i = 0; i < 100; i++) {
        const element = [...document.querySelectorAll(selector)].find((el) => !text || el.textContent.includes(text));
        if (element) {
            return element;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(`${selector} ${text || ""} not shown`);
};
"""


@tagged('post_install', '-at_install')
class TestOmWhatsappDeviceUi(HttpCase):
    """ The Link WhatsApp window of an account, in the browser, with a fake
    WhatsApp Bridge. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env.ref('base.user_admin')
        admin.groups_id = [Command.link(cls.env.ref('om_whatsapp_base.group_om_whatsapp_manager').id)]
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Browser', 'provider': 'device', 'user_ids': [Command.set(admin.ids)],
        })
        cls.env['ir.config_parameter'].sudo().set_param('om_whatsapp_device.autostart', False)
        cls.url = f'/web#action=om_whatsapp_base.om_whatsapp_account_action&id={cls.account.id}&view_type=form'

    def _on_status(self, bridge, answer):
        """ ``answer(count)`` changes the session before the bridge tells
        it, at each time the window asks its state. """
        request = bridge.request
        asked = []

        def on_request(this, method, path, json=None, timeout=None):
            if (method, path) == ('GET', f'/sessions/{self.account.device_key}'):
                asked.append(path)
                answer(len(asked))
            return request(this, method, path, json=json, timeout=timeout)

        bridge.request = on_request
        return asked

    def test_the_qr_code_live_until_linked(self):
        """ WhatsApp changes the QR code every few seconds: the window shows
        the new one, then linked, and stops asking. """
        with fake_bridge() as bridge:
            linked_at = []

            def answer(count):
                session = bridge.sessions[self.account.device_key]
                if count == 1:
                    session['qr_image'] = 'data:image/png;base64,ONE'
                elif count == 2:
                    session['qr_image'] = 'data:image/png;base64,TWO'
                else:
                    bridge.link(self.account.device_key)
                    linked_at.append(count)

            asked = self._on_status(bridge, answer)
            self.browser_js(self.url, WAIT_FOR + """
                (async () => {
                    await waitFor(".o_form_statusbar button[name=action_device_start_bridge]");
                    await waitFor(".alert-info", "Link your WhatsApp in a few steps");
                    (await waitFor(".o_form_statusbar button[name=action_device_link]")).click();
                    await waitFor(".modal .o_om_whatsapp_device_qr[src*='ONE']");
                    await waitFor(".modal .o_om_whatsapp_device_qr[src*='TWO']");
                    await waitFor(".modal .o_om_whatsapp_device_link", "Linked to +96555551234");
                    // linked: the window stops asking
                    await new Promise((resolve) => setTimeout(resolve, 5000));
                    (await waitFor(".modal .o_om_whatsapp_device_link button", "Close")).click();
                    await waitFor(".o_statusbar_status button[data-value=linked][aria-checked=true]");
                    console.log("test successful");
                })().catch((error) => console.error(error.message));
            """, login='admin', timeout=90)
        self.assertEqual(len(asked), linked_at[0], "the window asked again once linked")
        self.account.invalidate_cache()
        self.assertEqual(self.account.device_state, 'linked')

    def test_a_pairing_code_instead(self):
        with fake_bridge() as bridge:
            self.browser_js(self.url, WAIT_FOR + """
                (async () => {
                    (await waitFor(".o_form_statusbar button[name=action_device_link]")).click();
                    (await waitFor(".modal button", "Link with a phone number instead")).click();
                    const input = await waitFor(".modal .o_om_whatsapp_device_link input[type='tel']");
                    input.value = "+965 5555 1234";
                    input.dispatchEvent(new Event("input"));
                    (await waitFor(".modal button", "Get a code")).click();
                    await waitFor(".modal .o_om_whatsapp_device_code", "ABCD1234");
                    console.log("test successful");
                })().catch((error) => console.error(error.message));
            """, login='admin')
        self.assertEqual(bridge.sessions[self.account.device_key]['config']['pairing_phone'], '96555551234')

    def test_the_bridge_not_running_is_told(self):
        with fake_bridge() as bridge:

            def answer(count):
                bridge.running = False

            self._on_status(bridge, answer)
            self.browser_js(self.url, WAIT_FOR + """
                (async () => {
                    (await waitFor(".o_form_statusbar button[name=action_device_link]")).click();
                    await waitFor(".modal .o_om_whatsapp_device_link", "The WhatsApp Bridge is not running");
                    console.log("test successful");
                })().catch((error) => console.error(error.message));
            """, login='admin')
        self.account.invalidate_cache()
        self.assertEqual(self.account.device_state, 'offline')
