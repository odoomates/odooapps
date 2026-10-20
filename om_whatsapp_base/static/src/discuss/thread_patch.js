import { Thread } from "@mail/core/common/thread";
import { patch } from "@web/core/utils/patch";

/** A WhatsApp message sent keeps its header, for its ticks, even among quick ones. */
patch(Thread.prototype, {
    isSquashed(msg, prevMsg) {
        if (msg.notifications.some((notification) => notification.isWhatsapp)) {
            return false;
        }
        return super.isSquashed(...arguments);
    },
});
