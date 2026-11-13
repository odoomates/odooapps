import { Failure } from "@mail/core/common/failure_model";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

patch(Failure.prototype, {
    get iconSrc() {
        if (this.type === "om_whatsapp") {
            return "/om_whatsapp_base/static/description/icon.png";
        }
        return super.iconSrc;
    },
    get body() {
        if (this.type === "om_whatsapp") {
            if (this.notifications.length === 1 && this.lastMessage?.thread) {
                return _t("A WhatsApp message to “%(record_name)s” was not sent", {
                    record_name: this.lastMessage.thread.display_name,
                });
            }
            return _t("WhatsApp messages were not sent");
        }
        return super.body;
    },
});
