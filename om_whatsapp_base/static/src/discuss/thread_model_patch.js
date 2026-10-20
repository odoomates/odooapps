import { fields } from "@mail/core/common/record";
import { Thread } from "@mail/core/common/thread_model";
import { imageUrl } from "@web/core/utils/urls";
import { patch } from "@web/core/utils/patch";

/** A WhatsApp conversation is a chat with a customer: a new message opens its chat window, as a live chat does. */
patch(Thread.prototype, {
    setup() {
        super.setup(...arguments);
        this.appAsOmWhatsapp = fields.One("DiscussApp", {
            compute() {
                return this.isWhatsappConversation ? this.store.discuss : null;
            },
        });
    },
    get isWhatsappConversation() {
        return this.channel_type === "om_whatsapp";
    },
    get isChatChannel() {
        return this.isWhatsappConversation || super.isChatChannel;
    },
    get supportsCustomChannelName() {
        return !this.isWhatsappConversation && super.supportsCustomChannelName;
    },
    get avatarUrl() {
        if (this.isWhatsappConversation && this.avatar_cache_key && this.avatar_cache_key !== "no-avatar") {
            return imageUrl("discuss.channel", this.id, "avatar_128", { unique: this.avatar_cache_key });
        }
        return super.avatarUrl;
    },
    _computeDiscussAppCategory() {
        if (this.isWhatsappConversation) {
            return this.store.discuss.omWhatsapp;
        }
        return super._computeDiscussAppCategory();
    },
    get autoOpenChatWindowOnNewMessage() {
        return (
            (this.isWhatsappConversation && Boolean(this.self_member_id) && !this.store.chatHub.compact) ||
            super.autoOpenChatWindowOnNewMessage
        );
    },
    get inChathubOnNewMessage() {
        if (this.isWhatsappConversation) {
            return Boolean(this.self_member_id) && !this.store.discuss.isActive;
        }
        return super.inChathubOnNewMessage;
    },
    /** A minimised conversation opens too: a customer waits for an answer. */
    async notifyMessageToUser(message) {
        const chatWindow = this.isWhatsappConversation && this.store.ChatWindow.get({ thread: this });
        const minimised = chatWindow && !chatWindow.isOpen;
        await super.notifyMessageToUser(...arguments);
        if (
            minimised &&
            this.self_member_id &&
            !this.self_member_id.mute_until_dt &&
            !this.store.chatHub.compact &&
            this.store.chatHub.opened.length < this.store.chatHub.maxOpened
        ) {
            chatWindow.open();
        }
    },
});
