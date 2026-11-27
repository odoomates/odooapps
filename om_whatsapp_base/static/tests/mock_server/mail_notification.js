import { MailNotification } from "@mail/../tests/mock_server/mock_models/mail_notification";
import { patch } from "@web/core/utils/patch";

// Mirrors om_social_base/models/mail_notification.py: the channel of a message, WhatsApp here.
patch(MailNotification.prototype, {
    _store_notification_fields(res) {
        super._store_notification_fields(...arguments);
        res.attr("om_social_channel", () => "whatsapp", {
            predicate: (notification) => notification.notification_type === "om_social",
        });
    },
});
