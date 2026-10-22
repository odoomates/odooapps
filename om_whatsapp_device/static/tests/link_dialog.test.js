import { defineMailModels, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, animationFrame, click, edit, waitFor } from "@odoo/hoot-dom";
import { defineModels, getService, models, onRpc } from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");

class OmWhatsappAccount extends models.Model {
    _name = "om.whatsapp.account";
}
defineMailModels();
defineModels([OmWhatsappAccount]);

const LINK = { type: "ir.actions.client", tag: "om_whatsapp_device_link", target: "new", params: { account_id: 7 } };

test("the QR code, live, until linked", async () => {
    // what the bridge says now: WhatsApp changes the QR code every few seconds
    let current = { state: "linking", qr_image: "data:image/png;base64,ONE" };
    const asked = [];
    onRpc("om.whatsapp.account", "device_link_status", ({ args }) => {
        asked.push(args[0][0]);
        return current;
    });
    await start();
    await getService("action").doAction(LINK);
    // the test runner keeps the address of an image in data-src
    await waitFor(".o_om_whatsapp_device_qr[data-src*='ONE']");
    current = { state: "linking", qr_image: "data:image/png;base64,TWO" };
    await advanceTime(2000);
    await waitFor(".o_om_whatsapp_device_qr[data-src*='TWO']");
    current = { state: "linked", number: "+96555551234" };
    await advanceTime(2000);
    await waitFor(".o_om_whatsapp_device_link:contains('Linked to +96555551234')");
    // linked: the window stops asking
    const count = asked.length;
    await advanceTime(10000);
    expect(asked.length).toBe(count);
    expect(new Set(asked)).toEqual(new Set([7]));
});

test("a pairing code instead", async () => {
    onRpc("om.whatsapp.account", "device_link_status", () => ({ state: "linking", qr_image: "data:image/png;base64,QR" }));
    onRpc("om.whatsapp.account", "device_link_with_code", ({ args }) => {
        expect(args).toEqual([[7], "+965 5555 1234"]);
        return { state: "linking", pairing_code: "ABCD1234" };
    });
    await start();
    await getService("action").doAction(LINK);
    await click("button:contains('Link with a phone number instead')");
    await animationFrame();
    await click(".o_om_whatsapp_device_link input[type='tel']");
    await edit("+965 5555 1234");
    await click("button:contains('Get a code')");
    await waitFor(".o_om_whatsapp_device_code:contains('ABCD1234')");
});

test("the bridge not running is told", async () => {
    onRpc("om.whatsapp.account", "device_link_status", () => ({
        state: "offline",
        reason: "The WhatsApp Bridge does not answer at http://127.0.0.1:8077: start it.",
    }));
    await start();
    await getService("action").doAction(LINK);
    await waitFor(".o_om_whatsapp_device_link:contains('The WhatsApp Bridge is not running')");
});
