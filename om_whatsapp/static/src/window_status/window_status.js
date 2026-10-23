import { ChatWindow } from "@mail/core/common/chat_window";
import { DiscussContent } from "@mail/core/public_web/discuss_content";
import { propComputed } from "@mail/utils/common/hooks";
import { computedUntilStale } from "@mail/utils/common/signal";
import { Component, types } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

const MINUTE = 60 * 1000;

function isMetaConversation(channel) {
    return channel?.channel_type === "om_whatsapp" && channel.om_whatsapp_provider === "meta";
}

/** How long free text is still accepted in a conversation of Meta, minute by minute. */
export class OmWhatsappWindowStatus extends Component {
    static template = "om_whatsapp.WindowStatus";

    setup() {
        super.setup();
        this.channel = propComputed("channel", types.object());
        this.status = computedUntilStale(
            () => {
                const until = this.channel().om_whatsapp_free_text_until;
                const left = until ? deserializeDateTime(until).ts - Date.now() : 0;
                if (left <= 0) {
                    return {
                        level: "closed",
                        text: _t("Templates only"),
                        title: _t("The contact has not written in the last 24 hours: WhatsApp accepts only an approved template until they answer."),
                    };
                }
                const minutes = Math.ceil(left / MINUTE);
                const hours = Math.floor(minutes / 60);
                return {
                    level: minutes <= 60 ? "ending" : "open",
                    text: hours
                        ? _t("Free text for %(hours)s h %(minutes)s min", { hours, minutes: minutes % 60 })
                        : _t("Free text for %(minutes)s min", { minutes }),
                    title: _t("WhatsApp accepts free text within 24 hours of the last message of the contact; templates after."),
                };
            },
            () => {
                const until = this.channel().om_whatsapp_free_text_until;
                const left = until ? deserializeDateTime(until).ts - Date.now() : 0;
                return left > 0 ? Math.min(left % MINUTE || MINUTE, left) : 60 * MINUTE;
            }
        );
    }
}

Object.assign(DiscussContent.components, { OmWhatsappWindowStatus });
Object.assign(ChatWindow.components, { OmWhatsappWindowStatus });

patch(DiscussContent.prototype, {
    get hasHeaderSubline() {
        return isMetaConversation(this.thread?.channel) || super.hasHeaderSubline;
    },
});

patch(ChatWindow.prototype, {
    get hasNameSubline() {
        return isMetaConversation(this.props.chatWindow?.channel) || super.hasNameSubline;
    },
});
