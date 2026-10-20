import { Record } from "@mail/core/common/record";
import { Thread } from "@mail/core/common/thread_model";
import { imageUrl } from "@web/core/utils/urls";
import { patch } from "@web/core/utils/patch";

/** A WhatsApp conversation is a chat with a customer: a new message opens its chat window, as a live chat does. */
patch(Thread.prototype, {
    setup() {
        super.setup(...arguments);
        this.appAsOmWhatsapp = Record.one("DiscussApp", {
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
        if (this.isWhatsappConversation && this.avatarCacheKey && this.avatarCacheKey !== "no-avatar") {
            return imageUrl("discuss.channel", this.id, "avatar_128", { unique: this.avatarCacheKey });
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
            (this.isWhatsappConversation && Boolean(this.selfMember) && !this.store.chatHub.compact) ||
            super.autoOpenChatWindowOnNewMessage
        );
    },
    get inChathubOnNewMessage() {
        if (this.isWhatsappConversation) {
            return Boolean(this.selfMember) && !this.store.discuss.isActive;
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
            this.selfMember &&
            !this.mute_until_dt &&
            !this.store.chatHub.compact &&
            this.store.chatHub.opened.length < this.store.chatHub.maxOpened
        ) {
            chatWindow.open();
        }
    },
});
