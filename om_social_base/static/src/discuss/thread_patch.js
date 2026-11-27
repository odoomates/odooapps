import { Thread } from "@mail/core/common/thread";
import { patch } from "@web/core/utils/patch";

/** A message sent keeps its header, for its ticks, even among quick ones. */
patch(Thread.prototype, {
    isSquashed(msg, prevMsg) {
        if (msg.notification_ids.some((notification) => notification.isSocial)) {
            return false;
        }
        return super.isSquashed(...arguments);
    },
});
