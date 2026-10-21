import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";
import { whatsappStatus } from "./status_service";

/** In a WhatsApp Web conversation, the message box says why a message would not go from this browser. */
patch(Composer.prototype, {
    get placeholder() {
        const channel = this.thread?.channel;
        if (
            !this.props.placeholder &&
            channel?.channel_type === "om_whatsapp" &&
            channel.om_whatsapp_provider === "web" &&
            whatsappStatus.blocking
        ) {
            return whatsappStatus.reason;
        }
        return super.placeholder;
    },
});
