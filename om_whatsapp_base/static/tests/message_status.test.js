import {
    click,
    contains,
    defineMailModels,
    openFormView,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { onRpc, serverState } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

async function prepare(notification_status) {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Alice", partner_share: true });
    pyEnv["mail.notification"].create({
        mail_message_id: pyEnv["mail.message"].create({
            author_id: serverState.partnerId,
            body: "Your order is ready",
            message_type: "om_whatsapp",
            model: "res.partner",
            res_id: partnerId,
        }),
        notification_status,
        notification_type: "om_whatsapp",
        res_partner_id: partnerId,
    });
    return partnerId;
}

test("a sent WhatsApp shows its icon and status", async () => {
    const partnerId = await prepare("sent");
    await start();
    await openFormView("res.partner", partnerId);
    await contains(".o-mail-Message-notification i.fa-whatsapp");
    await contains(".o-mail-Message-notification", { text: "WhatsApp" });
    await click(".o-mail-Message-notification");
    await contains(".o-mail-MessageNotificationPopover i.fa-check[title='Delivered']");
});

test("a failed WhatsApp of the user offers to send it again", async () => {
    const partnerId = await prepare("exception");
    const retried = [];
    onRpc("mail.message", "action_om_whatsapp_retry", ({ args }) => {
        retried.push(args[0]);
        return false;
    });
    await start();
    await openFormView("res.partner", partnerId);
    await contains(".o-mail-Message-notification.text-danger i");
    await click(".o-mail-Message-notification");
    await contains(".modal-title", { text: "WhatsApp not sent" });
    await click(".modal-footer button", { text: "Send Again" });
    await contains(".modal", { count: 0 });
    expect(retried.length).toBe(1);
});

test("the ticks of a WhatsApp: one when sent, two when delivered", async () => {
    const pendingId = await prepare("pending");
    await start();
    await openFormView("res.partner", pendingId);
    await contains(".o-om-whatsapp-ticks i.fa-check", { count: 1 });
});

test("two ticks when delivered", async () => {
    const sentId = await prepare("sent");
    await start();
    await openFormView("res.partner", sentId);
    await contains(".o-om-whatsapp-ticks[title='Delivered'] i.fa-check", { count: 2 });
});

test("no ticks while queued or failed", async () => {
    const queuedId = await prepare("ready");
    await start();
    await openFormView("res.partner", queuedId);
    await contains(".o-mail-Message-notification");
    await contains(".o-om-whatsapp-ticks", { count: 0 });
});
