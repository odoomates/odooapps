/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";

/** The WhatsApp tab of the messaging menu lists the WhatsApp conversations. */
registerPatch({
    name: "NotificationListView",
    fields: {
        filteredChannels: {
            compute() {
                if (this.filter === "om_whatsapp") {
                    return this.messaging.models["Channel"].all(
                        (channel) => channel.channel_type === "om_whatsapp" && channel.thread.isPinned
                    );
                }
                return this._super();
            },
        },
    },
});
