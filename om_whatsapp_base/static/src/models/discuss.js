/** @odoo-module **/

import { registerFieldPatchModel, registerInstancePatchModel } from "@mail/model/model_core";
import { one2one } from "@mail/model/model_field";

registerInstancePatchModel("mail.discuss", "om_whatsapp_base", {
    onInputQuickSearch(value) {
        if (!this.sidebarQuickSearchValue && this.categoryOmWhatsapp) {
            this.categoryOmWhatsapp.open();
        }
        return this._super(value);
    },
});

registerFieldPatchModel("mail.discuss", "om_whatsapp_base", {
    /** The WhatsApp conversations of the user, in their own category of Discuss. */
    categoryOmWhatsapp: one2one("mail.discuss_sidebar_category", {
        inverse: "discussAsOmWhatsapp",
        isCausal: true,
    }),
});
