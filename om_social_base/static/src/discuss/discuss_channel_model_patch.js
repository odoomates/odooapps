import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { patch } from "@web/core/utils/patch";
import { getSocialChannel } from "../channels";

/** A new message of a conversation of the Social Inbox opens its chat window, as a live chat does. */
patch(DiscussChannel.prototype, {
    get isSocialConversation() {
        return this.channel_type === "om_social";
    },
    get socialChannel() {
        return getSocialChannel(this.om_social_channel);
    },
    get chatChannelTypes() {
        return [...super.chatChannelTypes, "om_social"];
    },
    get autoOpenChatWindowOnNewMessage() {
        return (
            (this.isSocialConversation && Boolean(this.self_member_id) && !this.store.chatHub.compact) ||
            super.autoOpenChatWindowOnNewMessage
        );
    },
    get inChathubOnNewMessage() {
        if (this.isSocialConversation) {
            return Boolean(this.self_member_id);
        }
        return super.inChathubOnNewMessage;
    },
    /** A minimised conversation opens too: a customer waits for an answer. */
    async notifyMessageToUser(message) {
        const minimised = this.isSocialConversation && this.chatWindow && !this.chatWindow.isOpen;
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
        return !this.isSocialConversation && super.allowCalls;
    },
});
