import { registry } from "@web/core/registry";
import { getExtensionInfo, getPicture } from "./extension_bridge";
import { whatsappStatus } from "./status_service";

const ACCOUNT = "om.whatsapp.account";
const PICTURE_DELAY = 5 * 60000;

/**
 * Reads in WhatsApp Web the profile pictures of the customers without a photo
 * in Odoo (when the account shows them), a few at a time: Odoo says which.
 */
export async function fetchPictures(orm, me) {
    const phones = await orm.silent.call(ACCOUNT, "om_whatsapp_web_pictures_due", [me]);
    for (const phone of phones) {
        const answer = await getPicture(phone).catch(() => null);
        if (!answer?.ok) {
            continue; // asked again later
        }
        await orm.silent.call(ACCOUNT, "om_whatsapp_web_set_picture", [me, phone], {
            data: answer.data || false,
            url: answer.url || false,
        });
    }
    return phones.length;
}

export const whatsappPictureService = {
    dependencies: ["orm"],
    start(env, { orm }) {
        let running = false;
        const look = async () => {
            if (running || whatsappStatus.level !== "connected" || !whatsappStatus.me || !whatsappStatus.accountId) {
                return;
            }
            running = true;
            try {
                if ((await getExtensionInfo())?.features.includes("picture")) {
                    await fetchPictures(orm, whatsappStatus.me);
                }
            } catch (error) {
                console.warn("WhatsApp pictures not read:", error);
            } finally {
                running = false;
            }
        };
        setTimeout(look, 20000);
        setInterval(() => document.visibilityState === "visible" && look(), PICTURE_DELAY);
    },
};

registry.category("services").add("om_whatsapp_web_pictures", whatsappPictureService);
