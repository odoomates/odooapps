import { MessagingMenu } from "@mail/core/public_web/messaging_menu/messaging_menu";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(MessagingMenu.prototype, {
    openFailureView(failure, options) {
        if (failure.type !== "om_whatsapp") {
            return super.openFailureView(...arguments);
        }
        this.env.services.action.doAction("om_whatsapp_base.om_whatsapp_message_action", {
            additionalContext: { search_default_failed: 1 },
            newWindow: options?.isMiddleClick,
        });
    },
    getFailureNotificationName(failure) {
        if (failure.type === "om_whatsapp") {
            return _t("WhatsApp Failure: %(modelName)s", { modelName: failure.modelName });
        }
        return super.getFailureNotificationName(...arguments);
    },
});
