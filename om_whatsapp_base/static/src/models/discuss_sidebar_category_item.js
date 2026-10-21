/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { clear } from "@mail/model/model_field_command";

/** A WhatsApp conversation in the sidebar: its contact's photo, and its unread messages, as a chat. */
registerPatch({
    name: "DiscussSidebarCategoryItem",
    fields: {
        avatarUrl: {
            compute() {
                if (this.channel.channel_type === "om_whatsapp") {
                    return this.channel.omWhatsappAvatarUrl;
                }
                return this._super();
            },
        },
        categoryCounterContribution: {
            compute() {
                if (this.channel.channel_type === "om_whatsapp") {
                    return this.channel.localMessageUnreadCounter > 0 ? 1 : 0;
                }
                return this._super();
            },
        },
        counter: {
            compute() {
                if (this.channel.channel_type === "om_whatsapp") {
                    return this.channel.localMessageUnreadCounter;
                }
                return this._super();
            },
        },
        hasThreadIcon: {
            compute() {
                if (this.channel.channel_type === "om_whatsapp") {
                    return clear();
                }
                return this._super();
            },
        },
        hasUnpinCommand: {
            compute() {
                if (this.channel.channel_type === "om_whatsapp") {
                    return !this.channel.localMessageUnreadCounter;
                }
                return this._super();
            },
        },
    },
});
