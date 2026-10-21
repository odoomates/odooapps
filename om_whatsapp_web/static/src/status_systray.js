import { Component, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { whatsappStatus } from "./status_service";

/** In the top bar, for the users of a WhatsApp Web account: whether WhatsApp Web is connected in this browser. */
export class WhatsappWebStatusSystray extends Component {
    static template = "om_whatsapp_web.StatusSystray";
    static components = { Dropdown };
    static props = {};

    setup() {
        this.statusService = useService("om_whatsapp_web_status");
        this.action = useService("action");
        this.status = useState(whatsappStatus);
    }

    get title() {
        return {
            connected: _t("WhatsApp Web connected"),
            connecting: _t("WhatsApp Web connecting..."),
            disconnected: _t("WhatsApp Web not connected"),
            unknown: _t("WhatsApp Web"),
        }[this.status.level];
    }

    openWhatsapp() {
        this.statusService.openWhatsapp();
    }

    refresh() {
        this.statusService.refresh();
    }

    openAccounts() {
        this.action.doAction("om_whatsapp_base.om_whatsapp_account_action");
    }
}

registry.category("systray").add("om_whatsapp_web_status", { Component: WhatsappWebStatusSystray }, { sequence: 26 });
