import { Component, onWillStart, untrack } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { rpc, rpcBus } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { flowStore } from "./flow_store";

// the calls of the web client that the server traces
const TRACED_URL = /\/web\/dataset\/call_(kw|button)/;
// the calls that only read, never traced: no trace to fetch after them
const READ_METHODS = new Set([
    "read", "web_read", "search", "search_read", "web_search_read", "search_count",
    "name_search", "web_name_search", "read_group", "web_read_group", "formatted_read_group",
    "fields_get", "get_views", "onchange", "default_get", "has_access", "check_access",
]);
const TRACES_SHOWN = 30;

const KINDS = {
    call: { icon: "chevron_forward", label: "", className: "o_flow_call" },
    create: { icon: "add", label: _t("Created"), className: "o_flow_create" },
    write: { icon: "edit", label: _t("Updated"), className: "o_flow_write" },
    unlink: { icon: "delete", label: _t("Deleted"), className: "o_flow_unlink" },
};

// the story: an icon per kind of document, a colour per status
const DOCUMENT_ICONS = {
    "sale.order": "shopping_cart",
    "purchase.order": "shopping_basket",
    "stock.picking": "local_shipping",
    "account.move": "description",
    "account.payment": "payments",
    "mrp.production": "build",
    "project.task": "task",
    "res.partner": "person",
    "crm.lead": "person_add",
};
const LINE_ICONS = {
    "stock.move": "inventory_2",
    "stock.move.line": "inventory_2",
};
const STATE_CLASSES = {
    draft: "secondary", new: "secondary", sent: "info",
    sale: "success", purchase: "success", done: "success", posted: "success", paid: "success",
    confirmed: "warning", waiting: "warning", to_approve: "warning", progress: "info",
    assigned: "info", cancel: "danger",
};
const VERBS = {
    create: _t("created"),
    write: _t("updated"),
    unlink: _t("deleted"),
};
const LINE_VERBS = {
    create: _t("added"),
    write: _t("updated"),
    unlink: _t("removed"),
};

/**
 * The panel beside the screen: after each click that changed data, the tree
 * of what it did. A method, then the records it created, edited and deleted,
 * then the methods it called; every record opens in one click.
 */
export class FlowPanel extends Component {
    static template = "flow_visualizer.FlowPanel";

    setup() {
        this.store = flowStore;
        this.action = useService("action");
        this.notification = useService("notification");
        this.KINDS = KINDS;
        this.VERBS = VERBS;
        this.LINE_VERBS = LINE_VERBS;
        this.tracedCalls = new Set();
        this.lastId = 0;
        this.fetchTimer = null;
        useBus(rpcBus, "RPC:REQUEST", ({ detail }) =>
            untrack(() => {
                if (
                    this.store.enabled &&
                    TRACED_URL.test(detail.url) &&
                    !READ_METHODS.has(detail.data.params?.method)
                ) {
                    this.tracedCalls.add(detail.data.id);
                }
            })
        );
        useBus(rpcBus, "RPC:RESPONSE", ({ detail }) =>
            untrack(() => {
                if (this.tracedCalls.delete(detail.data.id)) {
                    clearTimeout(this.fetchTimer);
                    this.fetchTimer = setTimeout(() => this.fetch(), 100);
                }
            })
        );
        onWillStart(() => this.store.enabled && this.fetch());
    }

    async fetch() {
        const traces = await rpc(
            "/flow_visualizer/traces",
            { after_id: this.lastId },
            { silent: true }
        );
        if (!traces.length) {
            return;
        }
        this.lastId = Math.max(this.lastId, ...traces.map((trace) => trace.id));
        this.store.traces = [...traces, ...this.store.traces].slice(0, TRACES_SHOWN);
        this.store.selectedId = traces[0].id;
    }

    /** The trace of a step gone back before: it no longer happened. */
    get selectedUndone() {
        const id = this.store.selectedId;
        return (this.store.sim.steps || []).some((step) => step.trace_id === id && step.abandoned);
    }

    traceLabel(trace) {
        const time = trace.date ? trace.date.slice(11, 19) : "";
        const undone = (this.store.sim.steps || []).some((step) => step.trace_id === trace.id && step.abandoned);
        return `${time}  ${trace.name}${trace.state === "failed" ? " ✕" : ""}${undone ? " (undone)" : ""}`;
    }

    get selected() {
        return this.store.traces.find((trace) => trace.id === this.store.selectedId);
    }

    /** The tree of the selected trace, flattened: one row per node shown. */
    get rows() {
        const trace = this.selected;
        const rows = [];
        const visit = (nodes, depth) => {
            for (const node of nodes) {
                if (!this.isShown(node)) {
                    continue;
                }
                const key = `${trace.id}-${node.id}`;
                const children = node.children || [];
                const expanded = !this.store.collapsed[key];
                rows.push({ key, node, depth, expanded, hasChildren: children.length > 0, index: rows.length });
                if (expanded) {
                    visit(children, depth + 1);
                }
            }
        };
        if (trace) {
            visit(trace.tree, 0);
        }
        return rows;
    }

    /** The documents of the selected trace, each under the one that caused it. */
    get storyRows() {
        const story = this.selected?.story;
        if (!story) {
            return [];
        }
        const keys = new Set(story.documents.map((card) => card.key));
        const children = {};
        const roots = [];
        for (const card of story.documents) {
            if (card.parent && keys.has(card.parent) && card.parent !== card.key) {
                (children[card.parent] ||= []).push(card);
            } else {
                roots.push(card);
            }
        }
        const rows = [];
        const seen = new Set();
        const visit = (cards, depth) => {
            for (const card of cards) {
                if (seen.has(card.key)) {
                    continue;
                }
                seen.add(card.key);
                rows.push({ card, depth, index: rows.length });
                visit(children[card.key] || [], depth + 1);
            }
        };
        visit(roots, 0);
        return rows;
    }

    /** "Created 1 Delivery Orders · 2 Stock Moves": what the click made, in one line. */
    get storySummary() {
        const story = this.selected?.story;
        if (!story) {
            return [];
        }
        const counts = {};
        const add = (label, count) => (counts[label] = (counts[label] || 0) + count);
        for (const card of story.documents) {
            if (card.kind === "create") {
                add(card.type || card.model_label, 1);
            }
            for (const group of card.lines) {
                if (group.kind === "create") {
                    add(group.label, group.count);
                }
            }
        }
        return Object.entries(counts).map(([label, count]) => `${count} × ${label}`);
    }

    get entryCard() {
        return this.selected?.story?.documents.find((card) => card.kind === "clicked");
    }

    documentIcon(card) {
        return DOCUMENT_ICONS[card.model] || "article";
    }

    lineIcon(group) {
        return LINE_ICONS[group.model] || "format_list_bulleted";
    }

    stateClass(card) {
        return `text-bg-${STATE_CLASSES[card.state?.[0]] || "primary"}`;
    }

    cardStyle(row) {
        return `margin-left: ${row.depth * 1.25}rem; --o-flow-index: ${Math.min(row.index, 20)}`;
    }

    openCard(card) {
        if (card.exists) {
            this.openRecord(card.model, card.id);
        }
    }

    openGroup(group) {
        if (group.kind === "unlink") {
            return;
        }
        if (group.ids.length === 1) {
            this.openRecord(group.model, group.ids[0]);
        } else {
            this.openRecords({ label: group.label, model: group.model, ids: group.ids });
        }
    }

    setView(view) {
        this.store.view = view;
    }

    replay() {
        this.store.replay++;
    }

    isShown(node) {
        if (this.store.showTechnical) {
            return true;
        }
        if (node.kind === "call") {
            return (node.children || []).some((child) => this.isShown(child));
        }
        return !node.noise;
    }

    rowStyle(row) {
        return `padding-left: ${0.5 + row.depth * 1.1}rem; --o-flow-index: ${Math.min(row.index, 30)}`;
    }

    recordName(node, resId) {
        const record = (node.records || []).find((rec) => rec[0] === resId);
        return record ? record[1] : `#${resId}`;
    }

    hiddenCount(node) {
        return node.total - (node.records || []).length;
    }

    toggleRow(row) {
        this.store.collapsed[row.key] = row.expanded;
    }

    toggleTechnical(ev) {
        this.store.showTechnical = ev.target.checked;
    }

    selectTrace(ev) {
        this.store.selectedId = Number(ev.target.value);
    }


    openRecord(model, resId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openRecords(node) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: node.label,
            res_model: node.model,
            domain: [["id", "in", node.ids]],
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    openSource(trace) {
        if (trace.res_ids.length === 1) {
            this.openRecord(trace.model, trace.res_ids[0]);
        }
    }

    /** Open the code of a node: in the editor of this machine, else on its repository. */
    async openCode(node) {
        const result = await rpc("/flow_visualizer/open_code", { file: node.file, line: node.line });
        if (result.url) {
            window.open(result.url, "_blank", "noopener");
        } else if (result.opened) {
            this.notification.add(_t("Opened %s in %s", node.where, result.opened), { type: "success" });
        } else {
            this.notification.add(_t("No editor or repository found for %s", node.where), { type: "warning" });
        }
    }

    async clear() {
        await rpc("/flow_visualizer/clear", {}, { silent: true });
        this.store.traces = [];
        this.store.selectedId = null;
        this.store.collapsed = {};
    }

    async turnOff() {
        this.store.enabled = await rpc("/flow_visualizer/toggle", { enabled: false });
    }
}

registry.category("main_components").add("FlowVisualizerPanel", { Component: FlowPanel });
