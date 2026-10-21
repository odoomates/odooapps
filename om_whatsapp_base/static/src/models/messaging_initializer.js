/** @odoo-module **/

import { registerInstancePatchModel } from "@mail/model/model_core";
import { insertAndReplace } from "@mail/model/model_field_command";

registerInstancePatchModel("mail.messaging_initializer", "om_whatsapp_base", {
    _initResUsersSettings() {
        this.messaging.discuss.update({
            categoryOmWhatsapp: insertAndReplace({
                isServerOpen: true,
                name: this.env._t("WhatsApp"),
                serverStateKey: "om_whatsapp_category_open",
                sortComputeMethod: "last_action",
                supportedChannelTypes: ["om_whatsapp"],
            }),
        });
        this._super(...arguments);
    },
});
