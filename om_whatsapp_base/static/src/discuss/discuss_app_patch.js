/** @odoo-module **/

import { DiscussApp } from "@mail/core/common/discuss_app_model";
import { DiscussAppCategory } from "@mail/core/common/discuss_app_category_model";
import { Record } from "@mail/core/common/record";
import {
    DiscussSidebarCategories,
    discussSidebarCategoriesRegistry,
} from "@mail/discuss/core/web/discuss_sidebar_categories";
import { compareDatetime } from "@mail/utils/common/misc";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

/** The WhatsApp conversations of the user, in their own category of Discuss. */
patch(DiscussApp, {
    new(data) {
        const res = super.new(data);
        res.omWhatsapp = {
            extraClass: "o-mail-DiscussSidebarCategory-om-whatsapp",
            id: "om_whatsapp",
            name: _t("WhatsApp"),
            isOpen: true,
            canView: false,
            canAdd: false,
        };
        return res;
    },
});

patch(DiscussApp.prototype, {
    setup(env) {
        super.setup(env);
        this.omWhatsapp = Record.one("DiscussAppCategory");
    },
});

patch(DiscussAppCategory.prototype, {
    sortThreads(t1, t2) {
        if (this.id === "om_whatsapp") {
            return compareDatetime(t2.lastInterestDateTime, t1.lastInterestDateTime) || t2.id - t1.id;
        }
        return super.sortThreads(t1, t2);
    },
});

patch(DiscussSidebarCategories.prototype, {
    /** The WhatsApp category has no user setting to keep it folded: it folds in this page only. */
    async toggleCategory(category) {
        if (category.id === "om_whatsapp") {
            category.isOpen = !category.isOpen;
            return;
        }
        return super.toggleCategory(...arguments);
    },
});

discussSidebarCategoriesRegistry.add(
    "om_whatsapp",
    {
        predicate: (store) =>
            store.discuss.omWhatsapp.threads.some((thread) => thread.displayToSelf || thread.isLocallyPinned),
        value: (store) => store.discuss.omWhatsapp,
    },
    { sequence: 25 }
);
