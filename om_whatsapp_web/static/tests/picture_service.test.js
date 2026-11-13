import { describe, expect, test } from "@odoo/hoot";
import { fetchPictures } from "@om_whatsapp_web/picture_service";
import { fakeExtension } from "./fake_extension";

describe.current.tags("headless");

test("the pictures Odoo asks for are read in WhatsApp Web and kept", async () => {
    const requests = fakeExtension((request) => {
        if (request.phone === "32470111111") {
            return { ok: true, data: "iVBORw==", mimetype: "image/png" };
        }
        if (request.phone === "32470222222") {
            return { ok: true, url: "https://pps.whatsapp.net/v/photo.jpg" };
        }
        return { ok: true, none: true };
    });
    const calls = [];
    const orm = {
        silent: {
            async call(model, method, args, kwargs) {
                calls.push([method, args, kwargs]);
                return method === "om_whatsapp_web_pictures_due" ? ["32470111111", "32470222222", "32470333333"] : true;
            },
        },
    };
    expect(await fetchPictures(orm, "32470000000")).toBe(3);
    expect(requests.map((r) => [r.type, r.phone])).toEqual([
        ["picture", "32470111111"],
        ["picture", "32470222222"],
        ["picture", "32470333333"],
    ]);
    expect(calls.slice(1).map(([, args, kwargs]) => [args[1], kwargs])).toEqual([
        ["32470111111", { data: "iVBORw==", url: false }],
        ["32470222222", { data: false, url: "https://pps.whatsapp.net/v/photo.jpg" }],
        ["32470333333", { data: false, url: false }],
    ]);
});
