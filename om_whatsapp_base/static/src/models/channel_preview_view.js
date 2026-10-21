/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";

registerPatch({
    name: "ChannelPreviewView",
    fields: {
        imageUrl: {
            compute() {
                if (this.channel.channel_type === "om_whatsapp") {
                    return this.channel.omWhatsappAvatarUrl;
                }
                return this._super();
            },
        },
    },
});
