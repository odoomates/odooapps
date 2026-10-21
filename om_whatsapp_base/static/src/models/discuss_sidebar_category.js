/** @odoo-module **/

import {
    registerFieldPatchModel,
    registerIdentifyingFieldsPatch,
    registerInstancePatchModel,
} from "@mail/model/model_core";
import { one2one } from "@mail/model/model_field";

registerFieldPatchModel("mail.discuss_sidebar_category", "om_whatsapp_base", {
    discussAsOmWhatsapp: one2one("mail.discuss", {
        inverse: "categoryOmWhatsapp",
        readonly: true,
    }),
});

registerIdentifyingFieldsPatch("mail.discuss_sidebar_category", "om_whatsapp_base", (identifyingFields) => {
    identifyingFields[0].push("discussAsOmWhatsapp");
});

/** The WhatsApp category has no user setting to keep it folded: it folds in this page only. */
registerInstancePatchModel("mail.discuss_sidebar_category", "om_whatsapp_base", {
    async close() {
        if (this.discussAsOmWhatsapp) {
            this.update({ isPendingOpen: false });
            return;
        }
        return this._super();
    },
    async open() {
        if (this.discussAsOmWhatsapp) {
            this.update({ isPendingOpen: true });
            return;
        }
        return this._super();
    },
});
