import {
    click,
    contains,
    defineMailModels,
    MENU_ACTIVE_IDS,
    openMessagingMenu,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, test } from "@odoo/hoot";
import { Command, serverState, withUser } from "@web/../tests/web_test_helpers";
import { rpc } from "@web/core/network/rpc";

describe.current.tags("desktop");
defineMailModels();

test("the WhatsApp tab lists the conversations of the user", async () => {
    const pyEnv = await startServer();
    const aliceId = pyEnv["res.partner"].create({ name: "Alice", partner_share: true });
    pyEnv["discuss.channel"].create([
        {
            name: "Alice",
            channel_type: "om_whatsapp",
            channel_member_ids: [
                Command.create({ partner_id: serverState.partnerId }),
                Command.create({ partner_id: aliceId }),
            ],
        },
        { name: "General", channel_type: "channel" },
    ]);
    await start();
    await openMessagingMenu(MENU_ACTIVE_IDS.OM_WHATSAPP);
    await contains(".o-mail-NotificationItem", { text: "Alice" });
    await contains(".o-mail-NotificationItem", { count: 1 });
});

test("the WhatsApp tab tells what it is for when empty", async () => {
    await startServer();
    await start();
    await openMessagingMenu(MENU_ACTIVE_IDS.OM_WHATSAPP);
    await contains(".o-mail-MessagingMenuEmpty", { text: "No WhatsApp conversation yet" });
});

test("a new message of a conversation opens its chat window", async () => {
    const pyEnv = await startServer();
    const otherPartnerId = pyEnv["res.partner"].create({ name: "Colleague" });
    const otherUserId = pyEnv["res.users"].create({ partner_id: otherPartnerId });
    const channelId = pyEnv["discuss.channel"].create({
        name: "Alice",
        channel_type: "om_whatsapp",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: otherPartnerId }),
        ],
    });
    await start();
    await contains(".o_menu_systray i[aria-label='Messages']");
    await contains(".o-mail-ChatWindow", { count: 0 });
    await withUser(otherUserId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "Is it ready?", message_type: "comment", subtype_xmlid: "mail.mt_comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        })
    );
    await contains(".o-mail-ChatWindow", { text: "Alice" });
    await contains(".o-mail-ChatWindow .o-mail-Message", { text: "Is it ready?" });
});

test("a new message opens a minimised conversation", async () => {
    const pyEnv = await startServer();
    const otherPartnerId = pyEnv["res.partner"].create({ name: "Colleague" });
    const otherUserId = pyEnv["res.users"].create({ partner_id: otherPartnerId });
    const channelId = pyEnv["discuss.channel"].create({
        name: "Alice",
        channel_type: "om_whatsapp",
        channel_member_ids: [
            Command.create({ partner_id: serverState.partnerId }),
            Command.create({ partner_id: otherPartnerId }),
        ],
    });
    await start();
    await openMessagingMenu(MENU_ACTIVE_IDS.OM_WHATSAPP);
    await click(".o-mail-NotificationItem", { text: "Alice" });
    await contains(".o-mail-ChatWindow", { text: "Alice" });
    await click(".o-mail-ChatWindow [title='Fold']");
    await contains(".o-mail-ChatBubble");
    await contains(".o-mail-ChatWindow", { count: 0 });
    await withUser(otherUserId, () =>
        rpc("/mail/message/post", {
            post_data: { body: "Hello?", message_type: "comment", subtype_xmlid: "mail.mt_comment" },
            thread_id: channelId,
            thread_model: "discuss.channel",
        })
    );
    await contains(".o-mail-ChatWindow .o-mail-Message", { text: "Hello?" });
});
