import { Composer } from "@mail/core/common/composer";
import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { whatsappStatus } from "./status_service";

/** In a WhatsApp Web conversation, the message box says why a message would not go from this browser. */
patch(Composer.prototype, {
    setup() {
        super.setup(...arguments);
        this.omWhatsappStatus = useState(whatsappStatus);
    },
    get placeholder() {
        const thread = this.thread;
        if (
            !this.props.placeholder &&
            thread?.channel_type === "om_whatsapp" &&
            thread.om_whatsapp_provider === "web" &&
            this.omWhatsappStatus.blocking
        ) {
            return this.omWhatsappStatus.reason;
        }
        return super.placeholder;
    },
});
