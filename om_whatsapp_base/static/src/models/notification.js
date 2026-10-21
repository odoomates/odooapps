/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";

/** The status of a WhatsApp message: ready is queued, pending sent, sent delivered. */
registerPatch({
    name: "Notification",
    modelMethods: {
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
    },
    fields: {
        /** Why a WhatsApp message failed, as its provider said. */
        failure_reason: attr(),
        iconClass: {
            compute() {
                if (this.isOmWhatsapp && ["pending", "sent"].includes(this.notification_status)) {
                    return "fa fa-check";
                }
                return this._super();
            },
        },
        iconTitle: {
            compute() {
                if (!this.isOmWhatsapp) {
                    return this._super();
                }
                if (this.om_whatsapp_read) {
                    return this.env._t("Read");
                }
                return {
                    ready: this.env._t("Queued"),
                    process: this.env._t("Sending"),
                    pending: this.env._t("Sent"),
                    sent: this.env._t("Delivered"),
                }[this.notification_status] || this._super();
            },
        },
        isOmWhatsapp: attr({
            compute() {
                return this.notification_type === "om_whatsapp";
            },
        }),
        om_whatsapp_read: attr({
            default: false,
        }),
    },
});
