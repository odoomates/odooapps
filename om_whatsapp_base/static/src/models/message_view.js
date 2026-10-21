/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";
import { clear } from "@mail/model/model_field_command";

registerPatch({
    name: "MessageView",
    fields: {
        failureNotificationIconClassName: {
            compute() {
                if (this.message && this.message.message_type === "om_whatsapp") {
                    return "fa fa-whatsapp";
                }
                return this._super();
            },
        },
        failureNotificationIconLabel: {
            compute() {
                if (this.message && this.message.message_type === "om_whatsapp") {
                    return this.env._t("WhatsApp");
                }
                return this._super();
            },
        },
        notificationIconClassName: {
            compute() {
                if (this.message && this.message.message_type === "om_whatsapp") {
                    return "fa fa-whatsapp";
                }
                return this._super();
            },
        },
        notificationIconLabel: {
            compute() {
                if (this.message && this.message.message_type === "om_whatsapp") {
                    return this.env._t("WhatsApp");
                }
                return this._super();
            },
        },
        /** The ticks of a WhatsApp message sent: one when sent, two when delivered, blue when read. */
        omWhatsappTicks: attr({
            compute() {
                const notification = this.message && this.message.notifications.find((n) => n.isOmWhatsapp);
                if (!notification || !["pending", "sent"].includes(notification.notification_status)) {
                    return clear();
                }
                const read = Boolean(notification.om_whatsapp_read);
                return { double: read || notification.notification_status === "sent", read, title: notification.iconTitle };
            },
        }),
    },
});
