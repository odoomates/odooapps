import { registry } from "@web/core/registry";
import { getExtensionInfo, sendReceipt } from "./extension_bridge";

/**
 * Returned by the WhatsApp Web provider when a user read a conversation or
 * played a voice message: the extension marks them read or played in
 * WhatsApp Web. Quiet: a receipt is not worth bothering the user.
 */
export async function receiptWhatsappWeb(env, action) {
    const info = await getExtensionInfo();
    if (info?.features.includes("receipt")) {
        const answer = await sendReceipt(action.params).catch((error) => ({ ok: false, error: error.message }));
        if (!answer.ok) {
            console.warn("WhatsApp receipt not sent:", answer.error);
        }
    }
    return { type: "ir.actions.act_window_close" };
}

registry.category("actions").add("om_whatsapp_web_receipt", receiptWhatsappWeb);
