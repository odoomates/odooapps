/** @odoo-module **/

import { registerInstancePatchModel } from "@mail/model/model_core";

/** The WhatsApp failures of several documents in the messaging menu open the failed messages. */
registerInstancePatchModel("mail.notification_group", "om_whatsapp_base", {
    openDocuments() {
        if (this.notification_type !== "om_whatsapp" || this.thread) {
            return this._super(...arguments);
        }
        this.env.bus.trigger("do-action", {
            action: "om_whatsapp_base.om_whatsapp_message_action",
            options: { additional_context: { search_default_failed: 1 } },
        });
        if (this.messaging.messagingMenu) {
            this.messaging.messagingMenu.close();
        }
    },
});
