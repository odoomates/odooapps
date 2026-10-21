/** @odoo-module **/

import { ComposerTextInput } from "@mail/components/composer_text_input/composer_text_input";
import { registerFieldPatchModel } from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";
import { patch } from "web.utils";

registerFieldPatchModel("mail.messaging", "om_whatsapp_web", {
    /** Why a message sent now would not go from this browser, from the status of WhatsApp Web. */
    omWhatsappWebBlockingReason: attr({
        default: "",
    }),
});

/** In a WhatsApp Web conversation, the message box says why a message would not go from this browser. */
patch(ComposerTextInput.prototype, "om_whatsapp_web", {
    get textareaPlaceholder() {
        const thread = this.composerView && this.composerView.composer.thread;
        if (
            thread &&
            thread.channel_type === "om_whatsapp" &&
            thread.om_whatsapp_provider === "web" &&
            this.messaging.omWhatsappWebBlockingReason
        ) {
            return this.messaging.omWhatsappWebBlockingReason;
        }
        return this._super();
    },
});
