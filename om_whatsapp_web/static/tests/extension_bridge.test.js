import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, waitUntil } from "@odoo/hoot-dom";
import { getExtensionVersion, sendThroughExtension } from "@om_whatsapp_web/extension_bridge";
import { fakeExtension } from "./fake_extension";

describe.current.tags("headless");

test("no extension: no version", async () => {
    const version = getExtensionVersion();
    await advanceTime(600);
    expect(await version).toBe(null);
});

test("ping and send", async () => {
    const requests = fakeExtension((request) =>
        request.type === "ping" ? { version: "1.0.0" } : { ok: request.message.phone === "32470123456" }
    );
    expect(await getExtensionVersion()).toBe("1.0.0");
    const answer = await sendThroughExtension({ phone: "32470123456", body: "Hi", attachments: [] });
    expect(answer.ok).toBe(true);
    await waitUntil(() => requests.length === 2);
    expect(requests.map((r) => [r.type, r.protocol])).toEqual([
        ["ping", 1],
        ["send", 1],
    ]);
});

test("answers of other pages are ignored", async () => {
    fakeExtension(() => ({ id: "not-this-one", version: "1.0.0" }));
    const version = getExtensionVersion();
    await advanceTime(600);
    expect(await version).toBe(null);
});
