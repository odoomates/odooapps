/** @odoo-module **/

import { NotificationGroup } from "@mail/components/notification_group/notification_group";
import { patch } from "web.utils";

patch(NotificationGroup.prototype, "om_whatsapp_base", {
    image() {
        if (this.group && this.group.notification_type === "om_whatsapp") {
            return "/om_whatsapp_base/static/description/icon.png";
        }
        return this._super(...arguments);
    },
});
