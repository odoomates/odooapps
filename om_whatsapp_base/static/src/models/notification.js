/** @odoo-module **/

import {
    registerClassPatchModel,
    registerFieldPatchModel,
    registerInstancePatchModel,
} from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";

/** The status of a WhatsApp message: ready is queued, pending sent, sent delivered. */
registerClassPatchModel("mail.notification", "om_whatsapp_base", {
    convertData(data) {
        const data2 = this._super(data);
        if ("failure_reason" in data) {
            data2.failure_reason = data.failure_reason;
        }
        if ("om_whatsapp_read" in data) {
            data2.om_whatsapp_read = data.om_whatsapp_read;
        }
        return data2;
    },
});

registerInstancePatchModel("mail.notification", "om_whatsapp_base", {
    _computeIsOmWhatsapp() {
        return this.notification_type === "om_whatsapp";
    },
    _computeOmWhatsappTitle() {
        if (!this.isOmWhatsapp) {
            return "";
        }
        if (this.om_whatsapp_read) {
            return this.env._t("Read");
        }
        return {
            ready: this.env._t("Queued"),
            process: this.env._t("Sending"),
            pending: this.env._t("Sent"),
            sent: this.env._t("Delivered"),
        }[this.notification_status] || "";
    },
});

registerFieldPatchModel("mail.notification", "om_whatsapp_base", {
    /** Why a WhatsApp message failed, as its provider said. */
    failure_reason: attr(),
    isOmWhatsapp: attr({
        compute: "_computeIsOmWhatsapp",
    }),
    om_whatsapp_read: attr({
        default: false,
    }),
    omWhatsappTitle: attr({
        compute: "_computeOmWhatsappTitle",
    }),
});
