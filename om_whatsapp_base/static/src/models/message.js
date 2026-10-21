/** @odoo-module **/

import { registerFieldPatchModel, registerInstancePatchModel } from "@mail/model/model_core";
import { attr } from "@mail/model/model_field";
import { clear } from "@mail/model/model_field_command";
import Dialog from "web.Dialog";

/** A click on the status of a failed WhatsApp message of the user offers to send it again. */
registerInstancePatchModel("mail.message", "om_whatsapp_base", {
    openResendAction() {
        if (this.message_type !== "om_whatsapp") {
            return this._super(...arguments);
        }
        const failure = this.failureNotifications.find((n) => n.isOmWhatsapp);
        if (!failure || !this.isCurrentUserOrGuestAuthor) {
            return;
        }
        Dialog.confirm(null, _.str.sprintf(this.env._t("%s\n\nSend it again?"), failure.failure_reason || ""), {
            title: this.env._t("WhatsApp not sent"),
            confirm_callback: async () => {
                const next = await this.env.services.rpc({
                    model: "mail.message",
                    method: "action_om_whatsapp_retry",
                    args: [[this.id]],
                });
                if (next) {
                    this.env.bus.trigger("do-action", { action: next });
                }
            },
        });
    },
    /** The ticks of a WhatsApp message sent: one when sent, two when delivered, blue when read. */
    _computeOmWhatsappTicks() {
        const notification = this.notifications.find((n) => n.isOmWhatsapp);
        if (!notification || !["pending", "sent"].includes(notification.notification_status)) {
            return clear();
        }
        const read = Boolean(notification.om_whatsapp_read);
        return { double: read || notification.notification_status === "sent", read, title: notification.omWhatsappTitle };
    },
});

registerFieldPatchModel("mail.message", "om_whatsapp_base", {
    omWhatsappTicks: attr({
        compute: "_computeOmWhatsappTicks",
    }),
});
