from odoo import Command
from odoo.tests import HttpCase, tagged

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
class TestOmWhatsappUi(HttpCase):
    """ The WhatsApp of Discuss, of the messaging menu and of the contacts, in
    the browser. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env.ref('base.user_admin')
        admin.groups_id = [Command.link(cls.env.ref('om_whatsapp_base.group_om_whatsapp_manager').id)]
        cls.account = cls.env['om.whatsapp.account'].create({
            'name': 'Browser', 'user_ids': [Command.set(admin.ids)],
        })
        cls.alice = cls.env['res.partner'].create({'name': 'Alice Browser', 'phone': '+32470123456'})
        sent = cls.alice.with_user(admin).sudo()._message_om_whatsapp(
            cls.account, 'Hello Alice', cls.alice.phone_sanitized, partner=cls.alice, om_whatsapp_id='wamid.ui1')
        sent._om_whatsapp_notifications()._om_whatsapp_set_status('sent')
        cls.account._om_whatsapp_update_status('wamid.ui1', 'read')
        cls.account._om_whatsapp_receive(cls.alice.phone_sanitized, 'When can you deliver?', 'wamid.ui2',
                                         quoted_id='wamid.ui1')
        cls.account._om_whatsapp_receive_reaction(cls.alice.phone_sanitized, 'wamid.ui1', '👍')
        for name, phone in [('Fail One', '+32470111111'), ('Fail Two', '+32470222222')]:
            partner = cls.env['res.partner'].create({'name': name, 'phone': phone})
            failed = partner.with_user(admin).sudo()._message_om_whatsapp(
                cls.account, 'Hi', partner.phone_sanitized, partner=partner)
            failed._om_whatsapp_notifications()._om_whatsapp_set_status('failed', 'The number is not on WhatsApp')
        # a contact form of its own: the one of Odoo asks for widgets of apps not installed here
        view = cls.env['ir.ui.view'].create({
            'name': 'res.partner.form.om_whatsapp.test',
            'model': 'res.partner',
            'type': 'form',
            'mode': 'primary',
            'arch': '''<form><sheet><field name="name"/><field name="phone" widget="phone"/></sheet>
                <div class="oe_chatter"><field name="message_ids"/></div></form>''',
        })
        cls.contact_action = cls.env['ir.actions.act_window'].create({
            'name': 'Contacts', 'res_model': 'res.partner', 'view_mode': 'form', 'view_id': view.id,
        })

    def test_discuss_and_messaging_menu(self):
        """ The conversation in the WhatsApp category, with its ticks and the
        reaction of the contact; the WhatsApp filter of the messaging menu,
        and its failures, which open the failed messages. """
        self.browser_js('/web#action=mail.action_discuss', WAIT_FOR + """
            (async () => {
                await waitFor(".o-mail-DiscussSidebarCategory-om-whatsapp");
                (await waitFor(".o-mail-DiscussSidebarChannel", "Alice Browser")).click();
                await waitFor(".o-om-whatsapp-ticks.text-info");
                await waitFor(".o-mail-MessageReaction", "👍");
                await waitFor(".o-mail-Message", "When can you deliver?");
                (await waitFor(".o_menu_systray i.fa-comments")).click();
                (await waitFor(".o-om-whatsapp-headerFilter")).click();
                await waitFor(".o-mail-NotificationItem", "Alice Browser");
                (await waitFor(".o-mail-MessagingMenu-header button", "All")).click();
                (await waitFor(".o-mail-NotificationItem img[src*='om_whatsapp_base']")).click();
                await waitFor(".o_breadcrumb", "WhatsApp Messages");
                await waitFor(".o_facet_value", "Failed");
                console.log("test successful");
            })().catch((error) => console.error(error.message));
        """, login='admin')

    def test_buttons_of_a_contact(self):
        """ The WhatsApp button of the chatter opens the composer on the
        contact; its phone has a WhatsApp button too. """
        url = f'/web#action={self.contact_action.id}&model=res.partner&id={self.alice.id}&view_type=form'
        self.browser_js(url, WAIT_FOR + """
            (async () => {
                await waitFor(".o_om_whatsapp_phone");
                // the chatter clicked once its thread is loaded
                await waitFor(".o-mail-Chatter .o-mail-Message", "Hello Alice");
                (await waitFor(".o-mail-Chatter-whatsapp")).click();
                await waitFor(".modal .modal-title", "Send WhatsApp");
                await waitFor(".modal .o_field_widget[name=number]");
                console.log("test successful");
            })().catch((error) => console.error(error.message));
        """, login='admin')
