import { after, describe, expect, test } from "@odoo/hoot";
import { translatedTerms, translationLoaded } from "@web/core/l10n/translation";
import { WhatsappReceiver } from "@om_whatsapp_web/receive_service";
import { fakeExtension } from "./fake_extension";

describe.current.tags("headless");

const ITEMS = [
    { key: "message:A1", kind: "message", id: "A1", phone: "32470123456", from_me: false, body: "Is it ready?" },
    { key: "message:B2", kind: "message", id: "B2", phone: "32470999999", from_me: false, body: "Private" },
    { key: "message:C3", kind: "message", id: "C3", phone: "32470123456", has_media: true, body: "the plan" },
    { key: "status:D4", kind: "status", id: "D4", ack: 3 },
];

/** The extension with ITEMS in its inbox; ``media`` answers the file requests. */
function extensionWith(media) {
    return fakeExtension((request) => {
        if (request.type === "inbox") {
            return { ok: true, me: "32470000000", items: ITEMS };
        }
        if (request.type === "media") {
            return media(request);
        }
        return { ok: true };
    });
}

function fakeOrm(accept = { account: true, accept: ["A1", "C3"] }) {
    const calls = [];
    return {
        calls,
        async call(model, method, args) {
            calls.push([method, args]);
            return method === "om_whatsapp_web_accept" ? accept : 1;
        },
    };
}

test("only the messages of known numbers reach Odoo, a file on its own after the rest", async () => {
    const requests = extensionWith(() => ({ ok: true, name: "plan.pdf", mimetype: "application/pdf", data: "JVBERg==" }));
    const orm = fakeOrm();
    expect(await new WhatsappReceiver(orm).pull()).toBe(3);

    const [[, [me, numbers]], [, [, plain]], [, [, withFile]]] = orm.calls;
    expect(me).toBe("32470000000");
    // the first call has the numbers only, never the text
    expect(numbers.map((n) => Object.keys(n).sort().join())).toEqual(["id,kind,phone,quoted_id,t", "id,kind,phone,quoted_id,t", "id,kind,phone,quoted_id,t"]);
    expect(plain.map((item) => item.id)).toEqual(["A1", "D4"]);
    expect(withFile.map((item) => item.id)).toEqual(["C3"]);
    expect(withFile[0].media).toEqual({ name: "plan.pdf", mimetype: "application/pdf", data: "JVBERg==" });
    expect(requests.filter((r) => r.type === "inbox-done").map((r) => r.keys)).toEqual([
        ["message:B2", "message:A1", "status:D4"],
        ["message:C3"],
    ]);
});

test("a file that cannot be read is tried again, then recorded without it", async () => {
    const requests = extensionWith(() => ({ ok: false, error: "WhatsApp Web is not open in this browser." }));
    const orm = fakeOrm();
    const receiver = new WhatsappReceiver(orm);
    await receiver.pull();
    // the others are not held back by it
    expect(requests.filter((r) => r.type === "inbox-done").flatMap((r) => r.keys)).toEqual([
        "message:B2",
        "message:A1",
        "status:D4",
    ]);
    await receiver.pull();
    const recorded = orm.calls.filter(([method]) => method === "om_whatsapp_web_receive").at(-1)[1][1];
    expect(recorded.map((item) => [item.id, item.media_error])).toEqual([["C3", "WhatsApp Web is not open in this browser."]]);
    expect(requests.filter((r) => r.type === "inbox-done").at(-1).keys).toEqual(["message:C3"]);
});

test("a file waits while WhatsApp Web is closed, without counting as a try", async () => {
    let open = false;
    const requests = extensionWith(() =>
        open
            ? { ok: true, name: "voice.ogg", mimetype: "audio/ogg", data: "T2dnUw==" }
            : { ok: false, retry: true, error: "WhatsApp Web is not open in this browser." }
    );
    const orm = fakeOrm();
    const receiver = new WhatsappReceiver(orm);
    for (let i = 0; i < 3; i++) {
        await receiver.pull();
    }
    const received = () => orm.calls.filter(([method]) => method === "om_whatsapp_web_receive").flatMap(([, [, items]]) => items);
    expect(received().map((item) => item.id)).not.toInclude("C3");
    expect(requests.filter((r) => r.type === "inbox-done").flatMap((r) => r.keys)).not.toInclude("message:C3");
    open = true;
    await receiver.pull();
    const voice = received().find((item) => item.id === "C3");
    expect(voice.media.name).toBe("voice.ogg");
    expect(voice.media_error).toBe(undefined);
});

test("another WhatsApp than the accounts of the user is kept, and told once", async () => {
    // the warning is translated: no translation, but loaded
    const loaded = translatedTerms[translationLoaded];
    translatedTerms[translationLoaded] = true;
    after(() => (translatedTerms[translationLoaded] = loaded));
    const requests = extensionWith(() => ({ ok: true }));
    const orm = fakeOrm({ account: false, accept: [] });
    const told = [];
    const receiver = new WhatsappReceiver(orm, { add: (message, options) => told.push([String(message), options.type]) });
    expect(await receiver.pull()).toBe(0);
    await receiver.pull();
    expect(orm.calls.map(([method]) => method)).toEqual(["om_whatsapp_web_accept", "om_whatsapp_web_accept"]);
    expect(requests.filter((request) => request.type === "inbox-done")).toEqual([]);
    expect(told.length).toBe(1);
    expect(told[0][0]).toInclude("+32470000000");
    expect(told[0][1]).toBe("warning");
});
