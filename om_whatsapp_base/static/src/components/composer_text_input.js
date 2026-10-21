/** @odoo-module **/

import { ComposerTextInput } from "@mail/components/composer_text_input/composer_text_input";
import { patch } from "web.utils";

/** In a WhatsApp conversation whose 24 hours are over, the message box says why free text is refused. */
patch(ComposerTextInput.prototype, "om_whatsapp_base", {
    get textareaPlaceholder() {
        const thread = this.composerView && this.composerView.composer.thread;
        const until = thread && thread.channel_type === "om_whatsapp" && thread.om_whatsapp_free_text_until;
        if (until && moment.utc(until) < moment.utc()) {
            return this.env._t(
                "24 hours since the last message of the contact: send an approved template from the contact or the document"
            );
        }
        return this._super();
    },
});
