import { Component, EventBus, onWillStart, proxy, untrack } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { browser } from "@web/core/browser/browser";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { rpc, rpcBus } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { flowStore } from "./flow_store";

const TRACED_URL = /\/web\/dataset\/call_(kw|button)/;
const STEP_ICONS = {
    "sale.order": "shopping_cart",
    "purchase.order": "shopping_basket",
    "stock.picking": "local_shipping",
    "account.move": "description",
    "account.payment": "payments",
    "mrp.production": "build",
};

/** Ask the server for the simulation and its steps. */
export async function refreshSimulation() {
    flowStore.sim = await rpc("/flow_visualizer/sim/state", {}, { silent: true });
}

/** Start a simulation, after saying what it means. */
export function startSimulation(dialog) {
    dialog.add(ConfirmationDialog, {
        title: _t("Start a simulation"),
        body: _t(
            "From now on nothing is saved for real: every click that changes data becomes a step you can go back to.\n\n" +
                "Keep all to save the steps, Discard to drop them. Stopping the server discards them too. " +
                "Emails are not sent and scheduled actions wait until the simulation ends."
        ),
        confirmLabel: _t("Start"),
        confirm: async () => {
            flowStore.sim = await rpc("/flow_visualizer/sim/start", {});
        },
        cancel: () => {},
    });
}

// what the systray asks the bar: keep, discard, back to the start
export const simulatorBus = new EventBus();

/**
 * The simulator bar, at the bottom of the screen while a simulation runs: the
 * steps made so far, as on a player; one click goes back to any of them.
 */
export class FlowSimulator extends Component {
    static template = "flow_visualizer.FlowSimulator";

    setup() {
        this.store = flowStore;
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.state = proxy({ showUndone: false, rewinding: "" });
        this.tracedCalls = new Set();
        useBus(rpcBus, "RPC:REQUEST", ({ detail }) =>
            untrack(() => {
                if (this.store.sim.active && TRACED_URL.test(detail.url)) {
                    this.tracedCalls.add(detail.data.id);
                }
            })
        );
        useBus(rpcBus, "RPC:RESPONSE", ({ detail }) =>
            untrack(() => {
                if (this.tracedCalls.delete(detail.data.id)) {
                    clearTimeout(this.timer);
                    this.timer = setTimeout(() => refreshSimulation(), 150);
                }
            })
        );
        onWillStart(() => this.store.sim.active && refreshSimulation());
        useBus(simulatorBus, "keep", () => this.end(true));
        useBus(simulatorBus, "discard", () => this.end(false));
        useBus(simulatorBus, "start-over", () => this.goBack(null));
    }

    get steps() {
        return (this.store.sim.steps || []).filter((step) => !step.abandoned);
    }

    get undone() {
        return (this.store.sim.steps || []).filter((step) => step.abandoned);
    }

    get current() {
        return this.steps.at(-1);
    }

    icon(step) {
        return STEP_ICONS[step.target_model] || "play_arrow";
    }

    label(step) {
        return step.action || step.name;
    }

    goBack(step) {
        if (this.store.simBusy || step === this.current) {
            return;
        }
        const later = step ? this.steps.length - this.steps.indexOf(step) - 1 : this.steps.length;
        const where = step ? `“${this.label(step)} ${step.target}”` : _t("the start");
        this.dialog.add(ConfirmationDialog, {
            title: _t("Go back in time"),
            body: _t("Go back to %(where)s? The %(count)s step(s) after it will be undone.", {
                where,
                count: later,
            }),
            confirmLabel: _t("Go back"),
            confirm: () => this.rewind(step),
            cancel: () => {},
        });
    }

    async rewind(step) {
        this.store.simBusy = true;
        this.state.rewinding = step ? `${this.label(step)} ${step.target}` : _t("the start");
        try {
            await rpc("/flow_visualizer/sim/rewind", { step_id: step ? step.id : 0 });
            await refreshSimulation();
            // the panel shows where one now is
            if (step && this.store.traces.some((trace) => trace.id === step.trace_id)) {
                this.store.selectedId = step.trace_id;
            }
            // let the rewind play a little: the screen then shows the step's document
            await new Promise((resolve) => setTimeout(resolve, 600));
            if (step?.target_id) {
                await this.action.doAction(
                    {
                        type: "ir.actions.act_window",
                        res_model: step.target_model,
                        res_id: step.target_id,
                        views: [[false, "form"]],
                        target: "current",
                    },
                    { clearBreadcrumbs: true }
                );
            } else {
                browser.location.reload();
            }
        } finally {
            this.store.simBusy = false;
            this.state.rewinding = "";
        }
    }

    end(keep) {
        this.dialog.add(ConfirmationDialog, {
            title: keep ? _t("Keep the simulation") : _t("Discard the simulation"),
            body: keep
                ? _t("Save the %s step(s) for real? This cannot be undone.", this.steps.length)
                : _t("Drop everything done since the simulation started?"),
            confirmLabel: keep ? _t("Keep all") : _t("Discard"),
            confirmClass: keep ? "btn-primary" : "btn-danger",
            confirm: async () => {
                this.store.simBusy = true;
                await rpc(keep ? "/flow_visualizer/sim/keep" : "/flow_visualizer/sim/discard", {});
                browser.location.reload();
            },
            cancel: () => {},
        });
    }

    toggleUndone() {
        this.state.showUndone = !this.state.showUndone;
    }
}

registry.category("main_components").add("FlowVisualizerSimulator", { Component: FlowSimulator });

/**
 * The simulator's own icon in the top bar: starts a simulation; while one
 * runs, it glows with the number of steps and holds keep, discard and back to
 * the start.
 */
export class SimulatorSystray extends Component {
    static template = "flow_visualizer.SimulatorSystray";
    static components = { Dropdown, DropdownItem };

    setup() {
        this.store = flowStore;
        this.dialog = useService("dialog");
    }

    get stepCount() {
        return (this.store.sim.steps || []).filter((step) => !step.abandoned).length;
    }

    start() {
        startSimulation(this.dialog);
    }

    send(request) {
        simulatorBus.trigger(request);
    }
}

registry.category("systray").add(
    "flow_visualizer_simulator",
    { Component: SimulatorSystray, isDisplayed: () => flowStore.allowed },
    { sequence: 29 }
);
