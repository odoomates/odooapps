/** @odoo-module **/

import { registerInstancePatchModel } from "@mail/model/model_core";

/** A WhatsApp conversation in the sidebar: its contact's photo, and its unread messages, as a chat. */
registerInstancePatchModel("mail.discuss_sidebar_category_item", "om_whatsapp_base", {
    _computeAvatarUrl() {
        if (this.channel.channel_type === "om_whatsapp") {
            return `/web/image/mail.channel/${this.channel.id}/avatar_128?unique=${this.channel.avatarCacheKey}`;
        }
        return this._super();
    },
    _computeCategoryCounterContribution() {
        if (this.channel.channel_type === "om_whatsapp") {
            return this.channel.localMessageUnreadCounter > 0 ? 1 : 0;
        }
        return this._super();
    },
    _computeCounter() {
        if (this.channel.channel_type === "om_whatsapp") {
            return this.channel.localMessageUnreadCounter;
        }
        return this._super();
    },
    _computeHasThreadIcon() {
        if (this.channel.channel_type === "om_whatsapp") {
            return false;
        }
        return this._super();
    },
    _computeHasUnpinCommand() {
        if (this.channel.channel_type === "om_whatsapp") {
            return !this.channel.localMessageUnreadCounter;
        }
        return this._super();
    },
});
