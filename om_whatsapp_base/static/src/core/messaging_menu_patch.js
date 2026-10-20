/** @odoo-module **/

import { Store } from "@mail/core/common/store_service";
import { MessagingMenu } from "@mail/core/web/messaging_menu";
import { _t } from "@web/core/l10n/translation";
import { session } from "@web/session";
import { patch } from "@web/core/utils/patch";

patch(Store.prototype, {
    /** The WhatsApp tab lists the WhatsApp conversations. */
    tabToThreadType(tab) {
        const threadTypes = super.tabToThreadType(tab);
        if (tab === "om_whatsapp") {
            threadTypes.push("om_whatsapp");
        }
        return threadTypes;
    },
});

patch(MessagingMenu.prototype, {
    get showOmWhatsappTab() {
        return Boolean(session.is_internal_user);
    },
    /** The WhatsApp conversations of the user, in their own tab. */
    get tabs() {
        const items = super.tabs;
        if (this.showOmWhatsappTab) {
            items.push({ icon: "fa fa-whatsapp", id: "om_whatsapp", label: _t("WhatsApp") });
        }
        return items;
    },
    /** The SMS app takes every failure that is not an email in openFailureView: WhatsApp ones are kept here. */
    onClickFailure(failure) {
        const threads = new Set(failure.notifications.map((n) => n.message?.originThread));
        if (failure.type !== "om_whatsapp" || threads.size === 1) {
            return super.onClickFailure(...arguments);
        }
        this.openOmWhatsappFailures();
    },
    openFailureView(failure) {
        if (failure.type !== "om_whatsapp") {
            return super.openFailureView(...arguments);
        }
        this.openOmWhatsappFailures();
    },
    openOmWhatsappFailures() {
        this.env.services.action.doAction("om_whatsapp_base.om_whatsapp_message_action", {
            additionalContext: { search_default_failed: 1 },
        });
        this.close();
    },
});
