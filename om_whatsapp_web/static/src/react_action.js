import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { getExtensionInfo, reactThroughExtension } from "./extension_bridge";

/**
 * Returned by the WhatsApp Web provider for a reaction a user made in Odoo:
 * the extension reacts in WhatsApp Web. Only a failure is told.
 */
export async function reactWhatsappWeb(env, action) {
    const { notification } = env.services;
    const fail = (reason) =>
        notification.add(_t("The reaction was not sent to WhatsApp: %(reason)s", { reason }), { type: "danger" });
    const info = await getExtensionInfo();
    if (!info) {
        fail(_t("the Odoo Mates WhatsApp Connector extension does not answer on this page."));
    } else if (!info.features.includes("react")) {
        fail(_t("update the Odoo Mates WhatsApp Connector extension (1.4.0 or later)."));
    } else {
        try {
            const answer = await reactThroughExtension(action.params);
            if (!answer.ok) {
                fail(answer.error || _t("WhatsApp Web did not take it."));
            }
        } catch (error) {
            fail(error.message === "timeout" ? _t("WhatsApp Web did not answer in time.") : error.message);
        }
    }
    return { type: "ir.actions.act_window_close" };
}

registry.category("actions").add("om_whatsapp_web_react", reactWhatsappWeb);
