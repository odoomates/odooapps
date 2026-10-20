/** @odoo-module **/

import { Record } from "@mail/core/common/record";
import { Thread } from "@mail/core/common/thread_model";
import { ThreadService } from "@mail/core/common/thread_service";
import { assignIn } from "@mail/utils/common/misc";
import { memoize } from "@web/core/utils/functions";
import { patch } from "@web/core/utils/patch";
import { url } from "@web/core/utils/urls";

// what the server tells of a WhatsApp conversation
const WHATSAPP_FIELDS = [
    "om_whatsapp_number",
    "om_whatsapp_has_contact",
    "om_whatsapp_provider",
    "om_whatsapp_free_text_until",
    "om_whatsapp_document_name",
];

/** A WhatsApp conversation is a chat with a customer, in the WhatsApp category of Discuss. */
patch(Thread.prototype, {
    update(data) {
        super.update(data);
        assignIn(this, data, WHATSAPP_FIELDS);
        if (this.type === "om_whatsapp") {
            this._store.discuss.omWhatsapp.threads.add(this);
        }
    },
    get isWhatsappConversation() {
        return this.type === "om_whatsapp";
    },
    get isChatChannel() {
        return this.isWhatsappConversation || super.isChatChannel;
    },
    get imgUrl() {
        if (this.isWhatsappConversation) {
            return url(`/discuss/channel/${this.id}/avatar_128`, { unique: this.avatarCacheKey });
        }
        return super.imgUrl;
    },
});

/** The last message of each WhatsApp conversation, for the messaging menu, as for the chats. */
patch(ThreadService.prototype, {
    setup(env, services) {
        super.setup(env, services);
        const fetchPreviews = this.fetchPreviews;
        this.fetchPreviews = memoize(async () => {
            await fetchPreviews();
            const ids = Object.values(this.store.Thread.records)
                .filter((thread) => thread.type === "om_whatsapp")
                .map((thread) => thread.id);
            if (!ids.length) {
                return;
            }
            const previews = await this.orm.call("discuss.channel", "channel_fetch_preview", [ids]);
            Record.MAKE_UPDATE(() => {
                for (const preview of previews) {
                    this.store.Message.insert(preview.last_message, { html: true });
                }
            });
        });
    },
});
