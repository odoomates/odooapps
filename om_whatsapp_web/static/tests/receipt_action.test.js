import { describe, expect, test } from "@odoo/hoot";
import { receiptWhatsappWeb } from "@om_whatsapp_web/receipt_action";
import { fakeExtension } from "./fake_extension";

describe.current.tags("headless");

const ACTION = { params: { phone: "32470123456", ids: ["3EB0R1"], kind: "read" } };

test("the extension marks them read", async () => {
    const requests = fakeExtension((request) =>
        request.type === "ping" ? { version: "1.6.0", features: ["send", "receive", "react", "status", "receipt"] } : { ok: true }
    );
    await receiptWhatsappWeb({ services: {} }, ACTION);
    expect(requests.map((r) => r.type)).toEqual(["ping", "receipt"]);
    expect(requests[1].receipt).toEqual(ACTION.params);
});

test("an older extension is left alone", async () => {
    const requests = fakeExtension(() => ({ version: "1.5.8", features: ["send", "receive", "react", "status"] }));
    await receiptWhatsappWeb({ services: {} }, ACTION);
    expect(requests.map((r) => r.type)).toEqual(["ping"]);
});
