import { Failure } from "@mail/core/common/failure_model";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { getSocialChannel } from "../channels";

patch(Failure.prototype, {
    get socialChannel() {
        return getSocialChannel(this.notifications[0]?.om_social_channel);
    },
    get iconSrc() {
        if (this.type === "om_social") {
            return this.socialChannel.iconSrc;
        }
        return super.iconSrc;
    },
    get body() {
        if (this.type === "om_social") {
            const channel = this.socialChannel.label;
            if (this.notifications.length === 1 && this.lastMessage?.thread) {
                return _t("A %(channel)s message to “%(record_name)s” was not sent", {
                    channel,
                    record_name: this.lastMessage.thread.display_name,
                });
            }
            return _t("%(channel)s messages were not sent", { channel });
        }
        return super.body;
    },
});
