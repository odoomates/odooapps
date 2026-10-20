import { Message } from "@mail/core/common/message";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

/** A click on the status of a failed WhatsApp message of the user offers to send it again. */
patch(Message.prototype, {
    /** The ticks of a WhatsApp message sent: one when sent, two when delivered, blue when read. */
    get whatsappTicks() {
        const notification = this.message.notifications.find((n) => n.isWhatsapp);
        if (!notification || !["pending", "sent"].includes(notification.notification_status)) {
            return null;
        }
        const read = Boolean(notification.om_whatsapp_read);
        return { double: read || notification.notification_status === "sent", read, title: notification.statusTitle };
    },
    onClickNotification(ev) {
        const failure = this.message.failureNotifications.find((n) => n.isWhatsapp);
        if (!failure || !this.message.isSelfAuthored) {
            return super.onClickNotification(ev);
        }
        const { action, dialog, orm } = this.env.services;
        dialog.add(ConfirmationDialog, {
            title: _t("WhatsApp not sent"),
            body: _t("%(reason)s\n\nSend it again?", { reason: failure.failureMessage }),
            confirmLabel: _t("Send Again"),
            confirm: async () => {
                const next = await orm.call("mail.message", "action_om_whatsapp_retry", [[this.message.id]]);
                if (next) {
                    await action.doAction(next);
                }
            },
            cancel: () => {},
        });
    },
});
