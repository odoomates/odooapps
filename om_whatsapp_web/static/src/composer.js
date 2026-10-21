/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";

registerPatch({
    name: "Messaging",
    fields: {
        /** Why a message sent now would not go from this browser, from the status of WhatsApp Web. */
        omWhatsappWebBlockingReason: attr({
            default: "",
        }),
    },
});

/** In a WhatsApp Web conversation, the message box says why a message would not go from this browser. */
registerPatch({
    name: "Composer",
    fields: {
        placeholder: {
            compute() {
                const channel = this.thread && this.thread.channel;
                if (
                    channel &&
                    channel.channel_type === "om_whatsapp" &&
                    channel.om_whatsapp_provider === "web" &&
                    this.messaging.omWhatsappWebBlockingReason
                ) {
                    return this.messaging.omWhatsappWebBlockingReason;
                }
                return this._super();
            },
        },
    },
});
