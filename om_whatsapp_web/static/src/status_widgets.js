import { Component, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { whatsappStatus } from "./status_service";

/** The status of WhatsApp Web in this browser, seen from an account: green only for its own number. */
function statusFor(resId) {
    const status = whatsappStatus;
    if (status.level === "connected" && status.accountId && resId && status.accountId !== resId) {
        return {
            level: "other",
            title: _t("Linked to another account in this browser"),
            reason: _t("WhatsApp Web in this browser is linked to %(account)s.", { account: status.accountName }),
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

class StatusBase extends Component {
    props = useProps({ ...standardWidgetProps });

    setup() {
        this.statusService = useService("om_whatsapp_web_status");
        this.status = whatsappStatus;
    }

    get view() {
        return statusFor(this.props.record?.resId);
    }

    openWhatsapp() {
        this.statusService.openWhatsapp();
    }

    refresh() {
        this.statusService.refresh();
    }
}

/** On the form of a WhatsApp Web account: the dot, why, what fixes it, and the last connection of anyone. */
export class WhatsappWebStatus extends StatusBase {
    static template = "om_whatsapp_web.Status";

    get lastSeen() {
        const { om_whatsapp_web_seen: seen, om_whatsapp_web_seen_user_id: by } = this.props.record.data;
        if (!seen) {
            return _t("Never connected yet.");
        }
        const when = seen.toRelative();
        return by?.display_name
            ? _t("Last connected %(when)s by %(user)s.", { when, user: by.display_name })
            : _t("Last connected %(when)s.", { when });
    }
}

/** A dot in the list of the accounts, for those of WhatsApp Web. */
export class WhatsappWebStatusDot extends StatusBase {
    static template = "om_whatsapp_web.StatusDot";
}

/** In the composer: a warning when a message sent now would not go from this browser. */
export class WhatsappWebStatusWarning extends StatusBase {
    static template = "om_whatsapp_web.StatusWarning";
}

registry.category("view_widgets").add("om_whatsapp_web_status", { component: WhatsappWebStatus });
registry.category("view_widgets").add("om_whatsapp_web_status_dot", { component: WhatsappWebStatusDot });
registry.category("view_widgets").add("om_whatsapp_web_status_warning", { component: WhatsappWebStatusWarning });
