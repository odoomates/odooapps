/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import widgetRegistry from "web.widgetRegistry";
import { whatsappStatus, whatsappStatusApi, whatsappStatusBus } from "./status_service";

const { Component } = owl;
const { onMounted, onWillUnmount } = owl.hooks;

/** The status of WhatsApp Web in this browser, seen from an account: green only for its own number. */
function statusFor(status, resId) {
    if (status.level === "connected" && status.accountId && resId && status.accountId !== resId) {
        return {
            level: "other",
            title: _t("Linked to another account in this browser"),
            reason: sprintf(_t("WhatsApp Web in this browser is linked to %(account)s."), { account: status.accountName }),
            action: null,
        };
    }
    const titles = {
        connected: _t("Connected in this browser"),
        connecting: _t("Connecting..."),
        disconnected: _t("Not connected in this browser"),
        unknown: _t("Connection unknown"),
    };
    return { level: status.level, title: titles[status.level], reason: status.reason, action: status.action };
}

/** Drawn again whenever the status changes. */
export function useWhatsappStatus(component) {
    onMounted(() => whatsappStatusBus.on("update", component, () => component.render()));
    onWillUnmount(() => whatsappStatusBus.off("update", component));
    return whatsappStatus;
}

class StatusBase extends Component {
    setup() {
        this.status = useWhatsappStatus(this);
    }

    get view() {
        return statusFor(this.status, this.props.record && this.props.record.res_id);
    }

    openWhatsapp() {
        whatsappStatusApi.openWhatsapp();
    }

    refresh() {
        whatsappStatusApi.refresh();
    }
}

/** On the form of a WhatsApp Web account: the dot, why, what fixes it, and the last connection of anyone. */
export class WhatsappWebStatus extends StatusBase {
    get lastSeen() {
        const data = this.props.record.data;
        const seen = data.om_whatsapp_web_seen;
        if (!seen) {
            return _t("Never connected yet.");
        }
        const when = seen.fromNow ? seen.fromNow() : moment(seen).fromNow();
        // a many2one of a legacy record is a datapoint: its name is in its data
        const by = data.om_whatsapp_web_seen_user_id;
        const user = by && by.data ? by.data.display_name : false;
        return user
            ? sprintf(_t("Last connected %(when)s by %(user)s."), { when, user })
            : sprintf(_t("Last connected %(when)s."), { when });
    }
}
WhatsappWebStatus.template = "om_whatsapp_web.Status";

/** A dot in the list of the accounts, for those of WhatsApp Web. */
export class WhatsappWebStatusDot extends StatusBase {}
WhatsappWebStatusDot.template = "om_whatsapp_web.StatusDot";

/** In the composer: a warning when a message sent now would not go from this browser. */
export class WhatsappWebStatusWarning extends StatusBase {}
WhatsappWebStatusWarning.template = "om_whatsapp_web.StatusWarning";

widgetRegistry.add("om_whatsapp_web_status", WhatsappWebStatus);
widgetRegistry.add("om_whatsapp_web_status_dot", WhatsappWebStatusDot);
widgetRegistry.add("om_whatsapp_web_status_warning", WhatsappWebStatusWarning);
