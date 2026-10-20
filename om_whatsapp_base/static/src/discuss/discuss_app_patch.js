import { Record } from "@mail/core/common/record";
import { DiscussApp } from "@mail/core/public_web/discuss_app_model";
import { DiscussAppCategory } from "@mail/core/public_web/discuss_app_category_model";
import { compareDatetime } from "@mail/utils/common/misc";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

/** The WhatsApp conversations of the user, in their own category of Discuss. */
patch(DiscussApp.prototype, {
    setup() {
        super.setup(...arguments);
        this.omWhatsapp = Record.one("DiscussAppCategory", {
            compute() {
                return {
                    extraClass: "o-mail-DiscussSidebarCategory-om-whatsapp",
                    icon: "fa fa-whatsapp",
                    id: "om_whatsapp",
                    name: _t("WhatsApp"),
                    sequence: 25,
                };
            },
        });
        this.omWhatsappThreads = Record.many("Thread", { inverse: "appAsOmWhatsapp" });
    },
});

patch(DiscussAppCategory.prototype, {
    sortThreads(t1, t2) {
        if (this.id === "om_whatsapp") {
            return compareDatetime(t2.lastInterestDt, t1.lastInterestDt) || t2.id - t1.id;
        }
        return super.sortThreads(...arguments);
    },
});
