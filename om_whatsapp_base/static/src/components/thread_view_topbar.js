/** @odoo-module **/

import { ThreadViewTopbar } from "@mail/components/thread_view_topbar/thread_view_topbar";
import { patch } from "web.utils";

/** The document a WhatsApp conversation last spoke about, and Create Contact for an unknown number. */
patch(ThreadViewTopbar.prototype, "om_whatsapp_base", {
    get omWhatsappThread() {
        const thread = this.threadViewTopbar && this.threadViewTopbar.thread;
        return thread && thread.channel_type === "om_whatsapp" ? thread : null;
    },
    onClickOmWhatsappCreateContact() {
        this.omWhatsappThread.omWhatsappCreateContact();
    },
    onClickOmWhatsappOpenDocument() {
        this.omWhatsappThread.omWhatsappOpenDocument();
    },
});
