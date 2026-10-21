/** @odoo-module **/

import { NotificationList } from "@mail/components/notification_list/notification_list";
import { patch } from "web.utils";

NotificationList._allowedFilters.push("om_whatsapp");

/** The WhatsApp tab of the messaging menu lists the WhatsApp conversations. */
patch(NotificationList.prototype, "om_whatsapp_base", {
    _getThreads(props) {
        if (props.filter === "om_whatsapp") {
            return this.messaging.models["mail.thread"]
                .all((thread) => thread.channel_type === "om_whatsapp" && thread.isPinned && thread.model === "mail.channel")
                .sort((c1, c2) => (c1.displayName < c2.displayName ? -1 : 1));
        }
        return this._super(...arguments);
    },
});
