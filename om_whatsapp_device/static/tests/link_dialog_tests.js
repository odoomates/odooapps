/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { click, editInput, getFixture, nextTick, patchWithCleanup } from "@web/../tests/helpers/utils";
import { createWebClient, doAction, getActionManagerServerData } from "@web/../tests/webclient/helpers";

const LINK = { type: "ir.actions.client", tag: "om_whatsapp_device_link", target: "new", params: { account_id: 7 } };

let serverData;
let target;
// the poll of the window, run by hand: WhatsApp changes the QR code every few seconds
let poll;
let polling;

async function tick() {
    if (polling) {
        poll();
    }
    await nextTick();
    await nextTick();
}

function mockDevice(handlers) {
    return (route, { model, method, args }) => {
        if (model === "om.whatsapp.account" && handlers[method]) {
            return handlers[method](args);
        }
    };
}

QUnit.module("om_whatsapp_device", (hooks) => {
    hooks.beforeEach(() => {
        serverData = getActionManagerServerData();
        target = getFixture();
        poll = null;
        polling = false;
        patchWithCleanup(browser, {
            setInterval(callback, delay) {
                if (delay !== 2000) {
                    return this._super(...arguments);
                }
                poll = callback;
                polling = true;
                return "om_whatsapp_device_poll";
            },
            clearInterval(id) {
                if (id !== "om_whatsapp_device_poll") {
                    return this._super(...arguments);
                }
                polling = false;
            },
        });
    });

    QUnit.module("Link dialog");

    QUnit.test("the QR code, live, until linked", async (assert) => {
        let current = { state: "linking", qr_image: "data:image/png;base64,ONE" };
        const asked = [];
        const webClient = await createWebClient({
            serverData,
            mockRPC: mockDevice({
                device_link_status: (args) => {
                    asked.push(args[0][0]);
                    return current;
                },
            }),
        });
        await doAction(webClient, LINK);
        // the test runner keeps the address of an image in data-src
        assert.containsOnce(target, ".modal .o_om_whatsapp_device_qr[data-src*='ONE']");
        current = { state: "linking", qr_image: "data:image/png;base64,TWO" };
        await tick();
        assert.containsOnce(target, ".modal .o_om_whatsapp_device_qr[data-src*='TWO']");
        current = { state: "linked", number: "+96555551234" };
        await tick();
        assert.ok(target.querySelector(".o_om_whatsapp_device_link").textContent.includes("Linked to +96555551234"));
        // linked: the window stops asking
        const count = asked.length;
        await tick();
        await tick();
        assert.strictEqual(asked.length, count);
        assert.deepEqual([...new Set(asked)], [7]);
    });

    QUnit.test("a pairing code instead", async (assert) => {
        const webClient = await createWebClient({
            serverData,
            mockRPC: mockDevice({
                device_link_status: () => ({ state: "linking", qr_image: "data:image/png;base64,QR" }),
                device_link_with_code: (args) => {
                    assert.deepEqual(args, [[7], "+965 5555 1234"]);
                    return { state: "linking", pairing_code: "ABCD1234" };
                },
            }),
        });
        await doAction(webClient, LINK);
        const showCode = [...target.querySelectorAll(".o_om_whatsapp_device_link button")].find((button) =>
            button.textContent.includes("Link with a phone number instead")
        );
        await click(showCode);
        await editInput(target, ".o_om_whatsapp_device_link input[type='tel']", "+965 5555 1234");
        const getCode = [...target.querySelectorAll(".o_om_whatsapp_device_link button")].find((button) =>
            button.textContent.includes("Get a code")
        );
        await click(getCode);
        await nextTick();
        assert.strictEqual(target.querySelector(".o_om_whatsapp_device_code").textContent, "ABCD1234");
    });

    QUnit.test("the bridge not running is told", async (assert) => {
        const webClient = await createWebClient({
            serverData,
            mockRPC: mockDevice({
                device_link_status: () => ({
                    state: "offline",
                    reason: "The WhatsApp Bridge does not answer at http://127.0.0.1:8077: start it.",
                }),
            }),
        });
        await doAction(webClient, LINK);
        assert.ok(
            target.querySelector(".o_om_whatsapp_device_link").textContent.includes("The WhatsApp Bridge is not running")
        );
    });
});
