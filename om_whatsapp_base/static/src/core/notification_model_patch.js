/** @odoo-module **/

import { Notification } from "@mail/core/common/notification_model";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

/** The status of a WhatsApp message: ready is queued, pending sent, sent delivered. */
patch(Notification.prototype, {
    get isWhatsapp() {
        return this.notification_type === "om_whatsapp";
    },
    /** Why a WhatsApp message failed, as its provider said. */
    get failureMessage() {
        return (this.isWhatsapp && this.failure_reason) || "";
    },
    get icon() {
        return this.isWhatsapp && !this.isFailure ? "fa fa-whatsapp" : super.icon;
    },
    get label() {
        return this.isWhatsapp ? _t("WhatsApp") : super.label;
    },
    get statusIcon() {
        if (this.isWhatsapp && ["pending", "sent"].includes(this.notification_status)) {
            return "fa fa-check";
        }
        return super.statusIcon;
    },
    get statusClass() {
        return this.isWhatsapp && this.om_whatsapp_read ? "text-info" : "";
    },
    get statusTitle() {
        if (this.isWhatsapp && this.om_whatsapp_read) {
            return _t("Read");
        }
        return super.statusTitle;
    },
});
