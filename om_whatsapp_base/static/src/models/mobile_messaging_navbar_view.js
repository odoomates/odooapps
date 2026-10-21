/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";

registerPatch({
    name: "MobileMessagingNavbarView",
    fields: {
        tabs: {
            compute() {
                const res = this._super();
                if (this.messaging.pinnedOmWhatsapps.length > 0) {
                    return [...res, { icon: "fa fa-whatsapp", id: "om_whatsapp", label: this.env._t("WhatsApp") }];
                }
                return res;
            },
        },
    },
});
