import { Notification } from "@mail/core/common/notification_model";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { getSocialChannel } from "../channels";

/** The status of a message of the Social Inbox: ready is queued, pending sent, sent delivered. */
patch(Notification.prototype, {
    get isSocial() {
        return this.notification_type === "om_social";
    },
    get socialChannel() {
        return getSocialChannel(this.om_social_channel);
    },
    get failureMessage() {
        if (this.isSocial && this.failure_reason) {
            return this.failure_reason;
        }
        return super.failureMessage;
    },
    get icon() {
        return this.isSocial && !this.isFailure ? this.socialChannel.icon : super.icon;
    },
    get label() {
        return this.isSocial ? this.socialChannel.label : super.label;
    },
    get statusIcon() {
        if (this.isSocial && ["pending", "sent"].includes(this.notification_status)) {
            return "check";
        }
        return super.statusIcon;
    },
    get statusClass() {
        if (this.isSocial && this.om_social_read) {
            return "text-info";
        }
        return super.statusClass;
    },
    get statusTitle() {
        if (this.isSocial && this.om_social_read) {
            return _t("Read");
        }
        return super.statusTitle;
    },
});
