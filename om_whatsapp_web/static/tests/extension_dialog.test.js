import { click, contains, defineMailModels, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, waitUntil } from "@odoo/hoot-dom";
import { getMockEnv, onRpc } from "@web/../tests/web_test_helpers";
import { sendWhatsappWeb } from "@om_whatsapp_web/send_action";
import { fakeExtension } from "./fake_extension";

describe.current.tags("desktop");
defineMailModels();

function mockMessages() {
    const calls = [];
    onRpc("mail.notification", "om_whatsapp_web_payload", () => [
        { id: 7, recipient: "Alice", phone: "32470123456", body: "Hi", attachments: [] },
    ]);
    onRpc("mail.notification", "om_whatsapp_web_done", ({ kwargs }) => {
        calls.push(["done", kwargs.error]);
        return true;
    });
    onRpc("mail.notification", "om_whatsapp_web_cancel", ({ args }) => {
        calls.push(["cancel", args[0]]);
        return true;
    });
    return calls;
}

/** Run the client action; its ping waits 0.5 s for the extension. */
async function send() {
    const next = sendWhatsappWeb(getMockEnv(), { params: { notification_ids: [7] } });
    await advanceTime(600);
    return next;
}

test("no extension: a dialog asks to allow this Odoo, then Send", async () => {
    const calls = mockMessages();
    await start();
    expect(await send()).toEqual({ type: "ir.actions.act_window_close" });
    await contains(".modal-title:text('Allow WhatsApp Web sending')");

    // still not allowed: the dialog stays, and says so
    await click(".modal-footer .btn-primary:text('Send')");
    await advanceTime(600);
    await contains(".o_om_whatsapp_still_missing");
    expect(calls).toEqual([]);

    // allowed in the extension: Send goes through it
    fakeExtension((request) => (request.type === "ping" ? { version: "1.0.4" } : { ok: true }));
    await click(".modal-footer .btn-primary:text('Send')");
    await contains(".modal-title:text('Allow WhatsApp Web sending')", { count: 0 });
    await waitUntil(() => calls.length === 1);
    expect(calls).toEqual([["done", false]]);
});

test("no extension: Cancel cancels the message", async () => {
    const calls = mockMessages();
    await start();
    await send();
    await click(".modal-footer button:text('Cancel')");
    await contains(".modal-title:text('Allow WhatsApp Web sending')", { count: 0 });
    await waitUntil(() => calls.length === 1);
    expect(calls).toEqual([["cancel", [7]]]);
});
