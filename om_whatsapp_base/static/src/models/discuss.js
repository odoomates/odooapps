/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { one } from "@mail/model/model_field";

registerPatch({
    name: "Discuss",
    recordMethods: {
        onInputQuickSearch(value) {
            if (!this.sidebarQuickSearchValue) {
                this.categoryOmWhatsapp.open();
            }
            return this._super(value);
        },
    },
    fields: {
        /** The WhatsApp conversations of the user, in their own category of Discuss. */
        categoryOmWhatsapp: one("DiscussSidebarCategory", {
            default: {},
            inverse: "discussAsOmWhatsapp",
        }),
    },
});
