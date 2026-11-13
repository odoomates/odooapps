import { after, beforeEach, describe, expect, test } from "@odoo/hoot";
import { translatedTerms, translationLoaded } from "@web/core/l10n/translation";
import { describeStatus } from "@om_whatsapp_web/status_service";

describe.current.tags("headless");

beforeEach(() => {
    // the reasons are translated: no translation, but loaded
    const loaded = translatedTerms[translationLoaded];
    translatedTerms[translationLoaded] = true;
    after(() => (translatedTerms[translationLoaded] = loaded));
});

const INFO = { version: "1.5.0", features: ["send", "receive", "react", "status"] };
const ACCOUNT = { id: 3, name: "Sales Team", phone: "+32 470 00 00 00" };

test("green: open, linked, the number of the account", () => {
    const status = describeStatus(INFO, { ok: true, tab: true, state: "ready", me: "32470000000", reader: true }, ACCOUNT);
    expect(status.level).toBe("connected");
    expect(status.blocking).toBe(false);
    expect(status.reason).toInclude("Sales Team");
});

test("red: no extension in this page, blocking", () => {
    const status = describeStatus(null, null, false);
    expect([status.level, status.blocking, status.action]).toEqual(["disconnected", true, "check"]);
});

test("red: WhatsApp Web closed, but sending opens it", () => {
    const status = describeStatus(INFO, { ok: true, tab: false }, false);
    expect([status.level, status.blocking, status.action]).toEqual(["disconnected", false, "open"]);
});

test("red: the QR code of a browser not linked, blocking", () => {
    const status = describeStatus(INFO, { ok: true, tab: true, state: "qr" }, false);
    expect([status.level, status.blocking, status.action]).toEqual(["disconnected", true, "open"]);
});

test("red: another number linked, blocking", () => {
    const status = describeStatus(INFO, { ok: true, tab: true, state: "ready", me: "32470999999" }, false);
    expect([status.level, status.blocking]).toEqual(["disconnected", true]);
    expect(status.reason).toInclude("+32470999999");
});

test("amber while loading, grey with an older extension", () => {
    expect(describeStatus(INFO, { ok: true, tab: true, state: "loading" }, false).level).toBe("connecting");
    const old = describeStatus({ version: "1.4.0", features: ["send", "receive", "react"] }, null, false);
    expect([old.level, old.blocking]).toEqual(["unknown", false]);
    expect(old.reason).toInclude("1.5.0");
});

test("red when the messages cannot be read, with the reason of the extension", () => {
    const status = describeStatus(INFO, { ok: true, tab: true, state: "ready", me: "32470000000", reader: false, error: "WhatsApp Web changed" }, ACCOUNT);
    expect([status.level, status.reason]).toEqual(["disconnected", "WhatsApp Web changed"]);
});
