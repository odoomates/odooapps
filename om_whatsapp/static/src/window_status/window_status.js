import { ChatWindow } from "@mail/core/common/chat_window";
import { DiscussContent } from "@mail/core/public_web/discuss_content";
import { Component, onWillUnmount, useState } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";

const MINUTE = 60 * 1000;

/** How long free text is still accepted in a conversation of Meta, minute by minute. */
export class OmWhatsappWindowStatus extends Component {
    static template = "om_whatsapp.WindowStatus";
    static props = ["thread"];

    setup() {
        super.setup();
        this.state = useState({ now: Date.now() });
        const interval = setInterval(() => (this.state.now = Date.now()), MINUTE / 2);
        onWillUnmount(() => clearInterval(interval));
    }

    get status() {
        const until = this.props.thread.om_whatsapp_free_text_until;
        const left = until ? deserializeDateTime(until).ts - this.state.now : 0;
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
    }
}

Object.assign(DiscussContent.components, { OmWhatsappWindowStatus });
Object.assign(ChatWindow.components, { OmWhatsappWindowStatus });
