/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";

/** The WhatsApp failures of the messaging menu open the failed messages. */
registerPatch({
    name: "NotificationGroup",
    recordMethods: {
        _openDocuments() {
            if (this.notification_type !== "om_whatsapp") {
                return this._super(...arguments);
            }
            this.env.services.action.doAction("om_whatsapp_base.om_whatsapp_message_action", {
                additionalContext: { search_default_failed: 1 },
            });
            this.messaging.messagingMenu.close();
        },
    },
});
