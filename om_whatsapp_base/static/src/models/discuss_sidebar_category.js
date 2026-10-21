/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { one } from "@mail/model/model_field";

registerPatch({
    name: "DiscussSidebarCategory",
    recordMethods: {
        /** The WhatsApp category has no user setting to keep it folded: it folds in this page only. */
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
    },
    fields: {
        categoryItemsOrderedByLastAction: {
            compute() {
                // the conversation of the last message on top, by the sort of the field
                if (this.discussAsOmWhatsapp) {
                    return this.categoryItems;
                }
                return this._super();
            },
        },
        discussAsOmWhatsapp: one("Discuss", {
            identifying: true,
            inverse: "categoryOmWhatsapp",
        }),
        isServerOpen: {
            compute() {
                if (this.discussAsOmWhatsapp) {
                    return true;
                }
                return this._super();
            },
        },
        name: {
            compute() {
                if (this.discussAsOmWhatsapp) {
                    return this.env._t("WhatsApp");
                }
                return this._super();
            },
        },
        orderedCategoryItems: {
            compute() {
                if (this.discussAsOmWhatsapp) {
                    return this.categoryItemsOrderedByLastAction;
                }
                return this._super();
            },
        },
        supportedChannelTypes: {
            compute() {
                if (this.discussAsOmWhatsapp) {
                    return ["om_whatsapp"];
                }
                return this._super();
            },
        },
    },
});
