import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import {
    deserializeDate,
    deserializeDateTime,
    formatDate,
    formatDateTime,
} from "@web/core/l10n/dates";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { STATIC_ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";
import { flowStore } from "./flow_store";

const DOCUMENT_ICONS = {
    "sale.order": "shopping_cart",
    "purchase.order": "shopping_basket",
    "stock.picking": "local_shipping",
    "account.move": "description",
    "account.payment": "payments",
    "mrp.production": "build",
    "project.task": "task",
    "crm.lead": "person_add",
};
const STATE_CLASSES = {
    draft: "secondary", new: "secondary", sent: "info", cancel: "danger",
    sale: "success", purchase: "success", done: "success", posted: "success",
    paid: "success", in_payment: "success", reconciled: "success",
    confirmed: "warning", waiting: "warning", to_approve: "warning", not_paid: "warning",
    partial: "warning", assigned: "info", progress: "info",
};
const EVENT_ICONS = {
    created: "add",
    milestone: "calendar_today",
    status: "arrow_forward",
};

function formatValue(value) {
    if (!value) {
        return "";
    }
    // a date has no time: shown as a day
    return value.length <= 10
        ? formatDate(deserializeDate(value))
        : formatDateTime(deserializeDateTime(value));
}

/**
 * The flow of an existing record: the documents linked to it as a journey
 * (the order, its deliveries, its invoices, their payments), then a timeline
 * of what happened to them and when.
 */
export class RecordFlowDialog extends Component {
    static template = "flow_visualizer.RecordFlowDialog";
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        model: t.string(),
        resId: t.number(),
        name: t.string().optional(""),
    });

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ flow: null, replay: 0, plan: null, target: null, busy: false });
        this.flowStore = flowStore;
        onWillStart(() => this.load());
    }

    get title() {
        return _t("Flow of %s", this.props.name || this.root?.name || "");
    }

    get documents() {
        return this.state.flow?.documents || [];
    }

    get root() {
        return this.documents.find((card) => card.key === this.state.flow?.root);
    }

    get byKey() {
        return Object.fromEntries(this.documents.map((card) => [card.key, card]));
    }

    /** The timeline, grouped by day. */
    get days() {
        const days = [];
        for (const [index, event] of (this.state.flow?.events || []).entries()) {
            const card = this.byKey[event.key];
            if (!card) {
                continue;
            }
            const day = this.eventDay(event);
            if (!days.length || days.at(-1).day !== day) {
                days.push({ day, events: [] });
            }
            days.at(-1).events.push({ ...event, index, card, time: this.eventTime(event) });
        }
        return days;
    }

    /** The day of an event, in the user's time zone. */
    eventDay(event) {
        if (!event.date) {
            return "";
        }
        return event.date.length <= 10
            ? formatDate(deserializeDate(event.date))
            : formatDate(deserializeDateTime(event.date));
    }

    eventTime(event) {
        if (!event.date || event.date.length <= 10) {
            return "";
        }
        return deserializeDateTime(event.date).toFormat("HH:mm");
    }

    icon(card) {
        return DOCUMENT_ICONS[card.model] || "article";
    }

    eventIcon(event) {
        return EVENT_ICONS[event.kind] || "circle";
    }

    stateClass(state) {
        return `text-bg-${STATE_CLASSES[state?.[0]] || "primary"}`;
    }

    /** The colour of a station: how far the document went. */
    stationClass(card) {
        const color = STATE_CLASSES[card.payment_state?.[0]] || STATE_CLASSES[card.state?.[0]] || "primary";
        return `o_flow_station_${color}${card.key === this.state.flow.root ? " o_flow_station_root" : ""}`;
    }

    mainMilestone(card) {
        const facts = card.milestones.filter((milestone) => !milestone.planned);
        const milestone = facts.at(-1) || card.milestones.at(-1);
        return milestone ? `${milestone.label} ${formatValue(milestone.date)}` : "";
    }

    parentName(card) {
        return card.parent && card.parent !== card.key ? this.byKey[card.parent]?.name : "";
    }

    eventText(event) {
        if (event.kind === "status") {
            return `${event.label}: ${event.old || "∅"} → ${event.new}`;
        }
        return event.label;
    }

    stationStyle(index) {
        return `--o-flow-index: ${Math.min(index, 20)}`;
    }

    open(card) {
        this.props.close();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: card.model,
            res_id: card.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    replay() {
        this.state.replay++;
    }

    async load() {
        this.state.flow = await rpc("/flow_visualizer/record", {
            model: this.props.model,
            res_id: this.props.resId,
        });
    }

    isLast(card) {
        return this.documents.at(-1) === card;
    }

    /** What going back to ``card`` would do: shown before anything changes. */
    async planBack(card) {
        this.state.target = card;
        this.state.plan = await rpc("/flow_visualizer/rewind/plan", {
            model: this.props.model,
            res_id: this.props.resId,
            target: card.key,
        });
    }

    get canApply() {
        return (this.state.plan || []).some((item) => item.steps.length && !item.blocked);
    }

    closePlan() {
        this.state.plan = null;
        this.state.target = null;
    }

    async applyBack() {
        this.state.busy = true;
        try {
            const done = await rpc("/flow_visualizer/rewind/apply", {
                model: this.props.model,
                res_id: this.props.resId,
                target: this.state.target.key,
            });
            this.notification.add(done.join("\n") || _t("Nothing to go back on."), {
                title: _t("Back to %s", this.state.target.name),
                type: "success",
            });
            this.closePlan();
            await this.load();
            this.replay();
        } finally {
            this.state.busy = false;
        }
    }
}

/** "Show Flow" in the gear menu of a saved record. */
export class RecordFlowMenuItem extends Component {
    static template = "flow_visualizer.RecordFlowMenuItem";
    static components = { DropdownItem };

    setup() {
        this.dialog = useService("dialog");
    }

    showFlow() {
        const root = this.env.model.root;
        this.dialog.add(RecordFlowDialog, {
            model: root.resModel,
            resId: root.resId,
            name: root.data.display_name || root.data.name || "",
        });
    }
}

registry.category("cogMenu").add(
    "flow_visualizer_record_flow",
    {
        Component: RecordFlowMenuItem,
        groupNumber: STATIC_ACTIONS_GROUP_NUMBER,
        isDisplayed: (env) => env.config.viewType === "form" && Boolean(env.model?.root?.resId),
    },
    { sequence: 60 }
);
