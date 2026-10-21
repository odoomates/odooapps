import { after, describe, expect, test } from "@odoo/hoot";
import { translatedTerms, translationLoaded } from "@web/core/l10n/translation";
import { reactWhatsappWeb } from "@om_whatsapp_web/react_action";
import { fakeExtension } from "./fake_extension";

describe.current.tags("headless");

const ACTION = { params: { phone: "32470123456", whatsapp_id: "3EB0AB", emoji: "👍" } };

function fakeEnv() {
    const loaded = translatedTerms[translationLoaded];
    translatedTerms[translationLoaded] = true;
    after(() => (translatedTerms[translationLoaded] = loaded));
    const notifications = [];
    const env = { services: { notification: { add: (message, options) => notifications.push([String(message), options.type]) } } };
    return { env, notifications };
}

test("the extension reacts, nothing is told", async () => {
    const requests = fakeExtension((request) =>
        request.type === "ping" ? { version: "1.4.0", features: ["send", "receive", "react"] } : { ok: true }
    );
    const { env, notifications } = fakeEnv();
    await reactWhatsappWeb(env, ACTION);
    expect(requests.map((r) => r.type)).toEqual(["ping", "react"]);
    expect(requests[1].reaction).toEqual(ACTION.params);
    expect(notifications).toEqual([]);
});

test("a failure is told with its reason", async () => {
    fakeExtension((request) =>
        request.type === "ping"
            ? { version: "1.4.0", features: ["send", "receive", "react"] }
            : { ok: false, error: "The message is not in WhatsApp Web." }
    );
    const { env, notifications } = fakeEnv();
    await reactWhatsappWeb(env, ACTION);
    expect(notifications).toEqual([
        ["The reaction was not sent to WhatsApp: The message is not in WhatsApp Web.", "danger"],
    ]);
});

test("an extension without reactions asks for an update", async () => {
    const requests = fakeExtension(() => ({ version: "1.3.0", features: ["send", "receive"] }));
    const { env, notifications } = fakeEnv();
    await reactWhatsappWeb(env, ACTION);
    expect(requests.map((r) => r.type)).toEqual(["ping"]);
    expect(notifications[0][0]).toInclude("1.4.0 or later");
});
