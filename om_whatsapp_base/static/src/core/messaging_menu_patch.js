import { MessagingMenu } from "@mail/core/public_web/messaging_menu";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";

patch(MessagingMenu.prototype, {
    get showOmWhatsappTab() {
        return user.isInternalUser;
    },
    /** The WhatsApp conversations of the user, in their own tab. */
    get _tabs() {
        const items = super._tabs;
        if (this.showOmWhatsappTab) {
            items.push({
                counter: this.store.discuss.omWhatsapp?.threadsWithCounter.length ?? 0,
                icon: "fa fa-whatsapp",
                id: "om_whatsapp",
                label: _t("WhatsApp"),
                sequence: 25,
            });
        }
        return items;
    },
    /** The SMS app takes every failure that is not an email in openFailureView: WhatsApp ones are kept here. */
    onClickFailure(failure) {
        const threads = new Set(failure.notifications.map((n) => (n.mail_message_id ?? n.message)?.thread));
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
        this.dropdown.close();
    },
    getFailureNotificationName(failure) {
        if (failure.type === "om_whatsapp") {
            return _t("WhatsApp Failure: %(modelName)s", { modelName: failure.modelName });
        }
        return super.getFailureNotificationName(...arguments);
    },
});
