/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { sprintf } from "@web/core/utils/strings";

/** A click on the status of a failed WhatsApp message of the user offers to send it again. */
registerPatch({
    name: "Message",
    recordMethods: {
        openResendAction() {
            if (this.message_type !== "om_whatsapp") {
                return this._super(...arguments);
            }
            const failure = this.failureNotifications.find((n) => n.isOmWhatsapp);
            if (!failure || !this.isCurrentUserOrGuestAuthor) {
                return;
            }
            const { action, dialog, orm } = this.env.services;
            dialog.add(ConfirmationDialog, {
                title: this.env._t("WhatsApp not sent"),
                body: sprintf(this.env._t("%(reason)s\n\nSend it again?"), { reason: failure.failure_reason || "" }),
                confirm: async () => {
                    const next = await orm.call("mail.message", "action_om_whatsapp_retry", [[this.id]]);
                    if (next) {
                        await action.doAction(next);
                    }
                },
                cancel: () => {},
            });
        },
    },
});
