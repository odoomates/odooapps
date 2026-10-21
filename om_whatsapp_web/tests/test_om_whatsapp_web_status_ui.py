from odoo import Command
from odoo.tests import HttpCase, tagged

WAIT_FOR = """
const waitFor = async (selector) => {
    for (let i = 0; i < 100; i++) {
        const element = document.querySelector(selector);
        if (element) {
            return element;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error(`${selector} not shown`);
};
"""


@tagged('post_install', '-at_install')
class TestOmWhatsappWebStatusUi(HttpCase):
    """ Without the extension, the account and the top bar show the red dot of
    a WhatsApp Web not connected in this browser (Odoo 16 lists have no dot). """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env.ref('base.user_admin')
        admin.groups_id = [Command.link(cls.env.ref('om_whatsapp_base.group_om_whatsapp_manager').id)]
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Browser', 'provider': 'web', 'user_ids': [Command.set(admin.ids)],
        })

    def test_red_dots_without_the_extension(self):
        action = 'om_whatsapp_base.om_whatsapp_account_action'
        self.browser_js(f'/web#action={action}&id={self.account.id}&view_type=form', WAIT_FOR + """
            (async () => {
                const status = await waitFor(".o_om_whatsapp_web_status");
                if (!status.querySelector(".o_om_whatsapp_dot_disconnected")) {
                    throw new Error("the account is not red");
                }
                await waitFor(".o_om_whatsapp_systray .o_om_whatsapp_dot_disconnected");
                console.log("test successful");
            })().catch((error) => console.error(error.message));
        """, login='admin')
