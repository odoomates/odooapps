import { after, describe, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { translatedTerms, translationLoaded } from "@web/core/l10n/translation";
import { sendWhatsappWeb } from "@om_whatsapp_web/send_action";
import { fakeExtension } from "./fake_extension";

describe.current.tags("headless");

function fakeServices() {
    // the notifications are translated: no translation, but loaded
    const loaded = translatedTerms[translationLoaded];
    translatedTerms[translationLoaded] = true;
    after(() => (translatedTerms[translationLoaded] = loaded));
    const calls = [];
    const notifications = [];
    const services = {
        orm: {
            async call(model, method, args, kwargs) {
                calls.push([method, kwargs]);
                if (method === "om_whatsapp_web_payload") {
                    return [{ id: 7, recipient: "Alice", phone: "32470123456", body: "Hi", attachments: [] }];
                }
                return true;
            },
        },
        notification: {
            add: (message, options) => notifications.push([String(message), options.type]),
        },
    };
    return { services, calls, notifications };
}

test("the dialog closes before WhatsApp answers", async () => {
    let release;
    const released = new Promise((resolve) => (release = resolve));
    fakeExtension(async (request) =>
        request.type === "ping" ? { version: "1.0.1" } : (await released, { ok: true, whatsapp_ids: ["3EB0AB", "3EB0CD"] })
    );
    const { services, calls, notifications } = fakeServices();

    const next = await sendWhatsappWeb({ services }, { params: { notification_ids: [7] } });
    expect(next).toEqual({ type: "ir.actions.act_window_close" });
    expect(calls.map(([method]) => method)).not.toInclude("om_whatsapp_web_done");

    release();
    await waitUntil(() => notifications.length === 2);
    expect(calls.at(-1)).toEqual(["om_whatsapp_web_done", { error: false, whatsapp_id: "3EB0AB" }]);
    expect(notifications).toEqual([
        ["Sending through WhatsApp Web...", "info"],
        ["WhatsApp sent to Alice.", "success"],
    ]);
});

test("a failure is told and recorded", async () => {
    fakeExtension((request) =>
        request.type === "ping" ? { version: "1.0.1" } : { ok: false, error: "This number is not on WhatsApp." }
    );
    const { services, calls, notifications } = fakeServices();

    await sendWhatsappWeb({ services }, { params: { notification_ids: [7] } });
    await waitUntil(() => notifications.length === 2);
    expect(calls.at(-1)).toEqual(["om_whatsapp_web_done", { error: "This number is not on WhatsApp." }]);
    expect(notifications[1]).toEqual(["WhatsApp to Alice not sent: This number is not on WhatsApp.", "danger"]);
});

test("messages asked fast go out one after the other, in order", async () => {
    let releaseFirst;
    const firstHeld = new Promise((resolve) => (releaseFirst = resolve));
    const requests = fakeExtension(async (request) => {
        if (request.type === "ping") {
            return { version: "1.1.0" };
        }
        if (request.message.body === "first") {
            await firstHeld;
        }
        return { ok: true };
    });
    const { services, calls } = fakeServices();
    services.orm.call = async (model, method, args, kwargs) => {
        calls.push([method, args, kwargs]);
        if (method === "om_whatsapp_web_payload") {
            const [id] = args[0];
            return [{ id, recipient: "Alice", phone: "32470123456", body: id === 1 ? "first" : "second", attachments: [] }];
        }
        return true;
    };

    await sendWhatsappWeb({ services }, { params: { notification_ids: [1] } });
    await sendWhatsappWeb({ services }, { params: { notification_ids: [2] } });
    await waitUntil(() => requests.some((r) => r.type === "send"));
    // the second waits: not even taken from Odoo while the first is in WhatsApp Web
    expect(requests.filter((r) => r.type === "send").map((r) => r.message.body)).toEqual(["first"]);
    expect(calls.filter(([method]) => method === "om_whatsapp_web_payload").length).toBe(1);

    releaseFirst();
    await waitUntil(() => calls.filter(([method]) => method === "om_whatsapp_web_done").length === 2);
    expect(requests.filter((r) => r.type === "send").map((r) => r.message.body)).toEqual(["first", "second"]);
    expect(calls.filter(([method]) => method === "om_whatsapp_web_done").map(([, args]) => args[0][0])).toEqual([1, 2]);
});

test("quick messages to the same contact share one notice", async () => {
    fakeExtension((request) => (request.type === "ping" ? { version: "1.1.3" } : { ok: true }));
    const { services, notifications } = fakeServices();
    const closed = [];
    services.notification.add = (message, options) => {
        notifications.push([String(message), options.type]);
        return () => closed.push(String(message));
    };
    for (const id of [1, 2, 3]) {
        await sendWhatsappWeb({ services }, { params: { notification_ids: [id] } });
    }
    await waitUntil(() => notifications.length === 2);
    expect(notifications).toEqual([
        ["Sending through WhatsApp Web...", "info"],
        ["3 WhatsApp messages sent to Alice.", "success"],
    ]);
    expect(closed).toEqual(["Sending through WhatsApp Web..."]);
});
