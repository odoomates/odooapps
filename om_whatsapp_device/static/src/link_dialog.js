import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const POLL_DELAY = 2000;

/**
 * Link a WhatsApp to an account: the QR code of the WhatsApp Bridge, live,
 * to scan from the phone as for WhatsApp Web; or a pairing code to type on
 * it. The window asks the state every two seconds, until linked.
 */
export class DeviceLink extends Component {
    static template = "om_whatsapp_device.DeviceLink";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.accountId = this.props.action.params.account_id;
        this.state = proxy({ status: { state: "connecting" }, withCode: false, phone: "", error: "" });
        onWillStart(() => this.refresh());
        this.timer = setInterval(() => this.refresh(), POLL_DELAY);
        onWillUnmount(() => clearInterval(this.timer));
    }

    async refresh() {
        try {
            this.state.status = await this.orm.call("om.whatsapp.account", "device_link_status", [[this.accountId]]);
        } catch (error) {
            this.state.error = error.data?.message || error.message;
        }
        if (this.state.status.state === "linked") {
            clearInterval(this.timer);
        }
    }

    async linkWithCode() {
        this.state.error = "";
        try {
            this.state.status = await this.orm.call("om.whatsapp.account", "device_link_with_code", [
                [this.accountId],
                this.state.phone,
            ]);
        } catch (error) {
            this.state.error = error.data?.message || error.message;
        }
    }

    close() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
        this.action.doAction({ type: "ir.actions.client", tag: "soft_reload" });
    }
}

registry.category("actions").add("om_whatsapp_device_link", DeviceLink);
