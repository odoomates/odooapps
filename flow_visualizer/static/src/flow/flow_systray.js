import { Component } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { flowStore } from "./flow_store";

/**
 * Turns the visualizer on and off for this session: while it is on, every
 * click that changes data is traced and shown in the panel.
 */
export class FlowSystray extends Component {
    static template = "flow_visualizer.FlowSystray";

    setup() {
        this.store = flowStore;
    }

    async toggle() {
        this.store.enabled = await rpc("/flow_visualizer/toggle", { enabled: !this.store.enabled });
    }
}

registry.category("systray").add(
    "flow_visualizer",
    { Component: FlowSystray, isDisplayed: () => flowStore.allowed },
    { sequence: 30 }
);
