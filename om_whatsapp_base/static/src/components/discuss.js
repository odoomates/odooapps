/** @odoo-module **/

import { Discuss } from "@mail/components/discuss/discuss";
import { patch } from "web.utils";

patch(Discuss.prototype, "om_whatsapp_base", {
    mobileNavbarTabs(...args) {
        return [...this._super(...args), { icon: "fa fa-whatsapp", id: "om_whatsapp", label: this.env._t("WhatsApp") }];
    },
});
