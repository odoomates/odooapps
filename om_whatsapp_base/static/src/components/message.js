/** @odoo-module **/

import { Message } from "@mail/components/message/message";
import { patch } from "web.utils";

/** A message of an unknown number has no author: it shows the WhatsApp picture of its conversation. */
patch(Message.prototype, "om_whatsapp_base", {
    get avatar() {
        const message = this.messageView.message;
        const thread = message.originThread;
        if (!message.author && !message.guestAuthor && thread && thread.channel_type === "om_whatsapp") {
            return `/web/image/mail.channel/${thread.id}/avatar_128?unique=${thread.avatarCacheKey}`;
        }
        return this._super();
    },
});
