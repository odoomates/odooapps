import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { patch } from "@web/core/utils/patch";

/** A new message of a WhatsApp conversation opens its chat window, as a live chat does. */
patch(DiscussChannel.prototype, {
    get isWhatsappConversation() {
        return this.channel_type === "om_whatsapp";
    },
    get chatChannelTypes() {
        return [...super.chatChannelTypes, "om_whatsapp"];
    },
    get autoOpenChatWindowOnNewMessage() {
        return (
            (this.isWhatsappConversation && Boolean(this.self_member_id) && !this.store.chatHub.compact) ||
            super.autoOpenChatWindowOnNewMessage
        );
    },
    get inChathubOnNewMessage() {
        if (this.isWhatsappConversation) {
            return Boolean(this.self_member_id);
        }
        return super.inChathubOnNewMessage;
    },
    /** A minimised conversation opens too: a customer waits for an answer. */
    async notifyMessageToUser(message) {
        const minimised = this.isWhatsappConversation && this.chatWindow && !this.chatWindow.isOpen;
        await super.notifyMessageToUser(...arguments);
        if (
            minimised &&
            this.self_member_id &&
            this.shouldNotifyMessageToUser(message) &&
            !this.store.chatHub.compact &&
            this.store.chatHub.opened.length < this.store.chatHub.maxOpened
        ) {
            await this.chatWindow?.open();
        }
    },
    get allowCalls() {
        return !this.isWhatsappConversation && super.allowCalls;
    },
});
