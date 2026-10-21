/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { deserializeDateTime } from "@web/core/l10n/dates";

const { DateTime } = luxon;

/** In a WhatsApp conversation whose 24 hours are over, the message box says why free text is refused. */
registerPatch({
    name: "Composer",
    fields: {
        placeholder: {
            compute() {
                const channel = this.thread && this.thread.channel;
                const until = channel && channel.channel_type === "om_whatsapp" && channel.om_whatsapp_free_text_until;
                if (until && deserializeDateTime(until) < DateTime.now()) {
                    return this.env._t(
                        "24 hours since the last message of the contact: send an approved template from the contact or the document"
                    );
                }
                return this._super();
            },
        },
    },
});
