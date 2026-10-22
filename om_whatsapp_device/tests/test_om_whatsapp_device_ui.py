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
class TestOmWhatsappDeviceLinkUi(HttpCase):
    """ The window that links WhatsApp, in the browser: the QR code of the
    bridge, live; a pairing code instead; the bridge not running. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env.ref('base.user_admin')
        admin.groups_id = [Command.link(cls.env.ref('om_whatsapp_base.group_om_whatsapp_manager').id)]
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Browser', 'provider': 'device', 'user_ids': [Command.set(admin.ids)],
        })
        # a database where the bridge was started from Odoo: the tests start none
        cls.env['ir.config_parameter'].sudo().set_param('om_whatsapp_device.autostart', False)
        cls.url = f'/web#action=om_whatsapp_base.om_whatsapp_account_action&id={cls.account.id}&view_type=form'

    def test_the_qr_code_live_until_linked(self):
        key = self.account.device_key
        answers = []
        with fake_bridge() as bridge:
            request = bridge.request

            def status_changes(client, method, path, json=None, timeout=None):
                # what the bridge says now: WhatsApp changes the QR code every few seconds
                if method == 'GET' and path == f'/sessions/{key}':
                    if len(answers) == 3:
                        bridge.link(key)
                    else:
                        bridge.sessions[key]['qr_image'] = 'data:image/png;base64,' + ('ONE' if len(answers) < 2 else 'TWO')
                    answer = request(client, method, path, json=json, timeout=timeout)
                    answers.append(answer['state'])
                    return answer
                return request(client, method, path, json=json, timeout=timeout)

            bridge.request = status_changes
            self.browser_js(self.url, WAIT_FOR + """
                (async () => {
                    (await waitFor("button[name=action_device_link]")).click();
                    await waitFor(".o_om_whatsapp_device_qr[src*='ONE']");
                    await waitFor(".o_om_whatsapp_device_qr[src*='TWO']");
                    await waitFor(".o_om_whatsapp_device_link", "Linked to +96555551234");
                    // linked: the window stops asking
                    await new Promise((resolve) => setTimeout(resolve, 5000));
                    console.log("test successful");
                })().catch((error) => console.error(error.message));
            """, login='admin')
        self.assertEqual(answers.count('open'), 1)
        self.account.invalidate_recordset()
        self.assertEqual((self.account.device_state, self.account.phone), ('linked', '+96555551234'))

    def test_a_pairing_code_instead(self):
        with fake_bridge() as bridge:
            self.browser_js(self.url, WAIT_FOR + """
                (async () => {
                    (await waitFor("button[name=action_device_link]")).click();
                    (await waitFor(".o_om_whatsapp_device_link button", "Link with a phone number instead")).click();
                    const input = await waitFor(".o_om_whatsapp_device_link input[type='tel']");
                    input.value = "+965 5555 1234";
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                    (await waitFor(".o_om_whatsapp_device_link button", "Get a code")).click();
                    await waitFor(".o_om_whatsapp_device_code", "ABCD1234");
                    console.log("test successful");
                })().catch((error) => console.error(error.message));
            """, login='admin')
        self.assertEqual(bridge.sessions[self.account.device_key]['config']['pairing_phone'], '96555551234')

    def test_the_bridge_not_running_is_told(self):
        with fake_bridge() as bridge:
            bridge.running = False
            self.browser_js(self.url, WAIT_FOR + """
                (async () => {
                    await waitFor(".o_form_view button[name=action_device_link]");
                    await odoo.__WOWL_DEBUG__.root.env.services.action.doAction({
                        type: "ir.actions.client", tag: "om_whatsapp_device_link", target: "new",
                        params: { account_id: ACCOUNT_ID },
                    });
                    await waitFor(".o_om_whatsapp_device_link", "The WhatsApp Bridge is not running");
                    console.log("test successful");
                })().catch((error) => console.error(error.message));
            """.replace('ACCOUNT_ID', str(self.account.id)), login='admin')
