import {
    click,
    contains,
    defineMailModels,
    openFormView,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { waitUntil } from "@odoo/hoot-dom";
import { mockService, mountWithCleanup, onRpc } from "@web/../tests/web_test_helpers";
import { Avatar } from "@mail/views/web/fields/avatar/avatar";

describe.current.tags("desktop");
defineMailModels();

let composers;
let inGroup;

beforeEach(() => {
    composers = [];
    inGroup = true;
    onRpc("has_group", ({ args }) => (args[1] === "om_whatsapp_base.group_om_whatsapp_user" ? inGroup : true));
    // the composer is a dialog of the server: only check it is asked for
    mockService("action", {
        doAction(action, options) {
            if (action?.res_model === "om.whatsapp.composer") {
                composers.push(action);
                return;
            }
            return super.doAction(action, options);
        },
    });
});

const PARTNER_FORM = `
    <form>
        <sheet><field name="name"/><field name="phone" widget="phone"/></sheet>
        <chatter/>
    </form>`;

async function openPartner(values) {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Wood Corner", phone: "+16238537197", ...values });
    await start();
    await openFormView("res.partner", partnerId, { arch: PARTNER_FORM });
    return { pyEnv, partnerId };
}

test("phone field: send to that number", async () => {
    const { partnerId } = await openPartner();
    await click(".o_field_phone .o_input");
    await click(".o_field_phone .o_om_whatsapp_phone");
    await waitUntil(() => composers.length === 1);
    expect(composers[0].context).toMatchObject({
        active_model: "res.partner",
        active_ids: [partnerId],
        om_whatsapp_number: "+16238537197",
    });
});

test("phone field: no button without the group, or when turned off", async () => {
    inGroup = false;
    await openPartner();
    await click(".o_field_phone .o_input");
    await contains(".o_field_phone .o_phone_form_link");
    await contains(".o_field_phone .o_om_whatsapp_phone", { count: 0 });
});

test("phone field: option enable_whatsapp", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "Wood Corner", phone: "+16238537197" });
    await start();
    await openFormView("res.partner", partnerId, {
        arch: `<form><field name="phone" widget="phone" options="{'enable_whatsapp': false}"/></form>`,
    });
    await click(".o_field_phone .o_input");
    await contains(".o_field_phone .o_phone_form_link");
    await contains(".o_field_phone .o_om_whatsapp_phone", { count: 0 });
});

test("chatter: WhatsApp next to Log note", async () => {
    const { partnerId } = await openPartner();
    await contains(".o-mail-Chatter-logNote + .o-mail-Chatter-whatsapp");
    await click(".o-mail-Chatter-whatsapp");
    await waitUntil(() => composers.length === 1);
    expect(composers[0].context).toMatchObject({ active_model: "res.partner", active_ids: [partnerId] });
    expect(composers[0].context.om_whatsapp_number).toBe(undefined);
});

test("chatter: no button without the group", async () => {
    inGroup = false;
    await openPartner();
    await contains(".o-mail-Chatter-logNote");
    await contains(".o-mail-Chatter-whatsapp", { count: 0 });
});

test("avatar card: WhatsApp for a contact with a phone", async () => {
    const pyEnv = await startServer();
    // the avatar card of Odoo 18 is the one of a user: the WhatsApp goes to their contact
    const [batmanPartnerId, robinPartnerId] = pyEnv["res.partner"].create([
        { name: "Batman", phone: "+15550100" },
        { name: "Robin" },
    ]);
    const [batmanId, robinId] = pyEnv["res.users"].create([
        { name: "Batman", partner_id: batmanPartnerId, phone: "+15550100" },
        { name: "Robin", partner_id: robinPartnerId },
    ]);
    await start();
    await mountWithCleanup(Avatar, { props: { resId: batmanId, resModel: "res.users", displayName: "Batman" } });
    await click(".o-mail-Avatar img");
    await click(".o_avatar_card .o_avatar_card_whatsapp");
    await waitUntil(() => composers.length === 1);
    expect(composers[0].context).toMatchObject({ active_model: "res.partner", active_ids: [batmanPartnerId] });

    await mountWithCleanup(Avatar, { props: { resId: robinId, resModel: "res.users", displayName: "Robin" } });
    await click(".o-mail-Avatar:contains('Robin') img");
    await contains(".o_avatar_card:contains('Robin')");
    await contains(".o_avatar_card:contains('Robin') .o_avatar_card_whatsapp", { count: 0 });
});
