/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { one } from "@mail/model/model_field";
import { clear } from "@mail/model/model_field_command";

registerPatch({
    name: "Thread",
    fields: {
        messagingAsPinnedOmWhatsapp: one("Messaging", {
            compute() {
                if (!this.messaging || !this.channel || this.channel.channel_type !== "om_whatsapp" || !this.isPinned) {
                    return clear();
                }
                return this.messaging;
            },
            inverse: "pinnedOmWhatsapps",
        }),
    },
});
