/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";

registerPatch({
    name: "NotificationGroupView",
    fields: {
        imageSrc: {
            compute() {
                if (this.notificationGroup.notification_type === "om_whatsapp") {
                    return "/om_whatsapp_base/static/description/icon.png";
                }
                return this._super();
            },
        },
    },
});
