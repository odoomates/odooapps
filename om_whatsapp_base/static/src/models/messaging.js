/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { many } from "@mail/model/model_field";

registerPatch({
    name: "Messaging",
    fields: {
        pinnedOmWhatsapps: many("Thread", {
            inverse: "messagingAsPinnedOmWhatsapp",
        }),
    },
});
