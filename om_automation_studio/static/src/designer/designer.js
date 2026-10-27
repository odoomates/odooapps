import { Component, onMounted, onWillStart, onWillUnmount, useExternalListener, useRef, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { DomainSelector } from "@web/core/domain_selector/domain_selector";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MODEL = "om.workflow";
const NODE_W = 216;
const NODE_H = 64;
// a step with several exits lists them under its header
const HEAD_H = 52;
const PORT_GAP = 24;
const GRID = 20;
// a press that moves less than this is a click, not a drag
const DRAG_THRESHOLD_PX = 4;
const HISTORY_SIZE = 80;

export const NODE_TYPES = {
    start: { label: _t("Start"), icon: "fa-play", group: "", ports: ["out"] },
    condition: { label: _t("Condition"), icon: "fa-sitemap", group: "logic", ports: ["yes", "no"] },
    wait: { label: _t("Wait"), icon: "fa-hourglass-half", group: "wait", ports: ["out"] },
    wait_until: { label: _t("Wait Until"), icon: "fa-calendar-check-o", group: "wait", ports: ["done", "timeout"] },
    approval: { label: _t("Approval"), icon: "fa-thumbs-up", group: "wait", ports: ["approved", "rejected", "timeout"] },
    update: { label: _t("Update Record"), icon: "fa-pencil", group: "action", ports: ["out"] },
    create: { label: _t("Create Record"), icon: "fa-plus-circle", group: "action", ports: ["out"] },
    email: { label: _t("Send Email"), icon: "fa-envelope", group: "action", ports: ["out"] },
    activity: { label: _t("Schedule Activity"), icon: "fa-clock-o", group: "action", ports: ["out"] },
    note: { label: _t("Post Message"), icon: "fa-comment", group: "action", ports: ["out"] },
    end: { label: _t("End"), icon: "fa-flag", group: "logic", ports: [] },
};
const PALETTE = [
    ["logic", _t("Logic")],
    ["wait", _t("Wait")],
    ["action", _t("Actions")],
];
const PORT_LABELS = {
    out: "",
    yes: _t("Yes"),
    no: _t("No"),
    done: _t("Met"),
    timeout: _t("Time limit"),
    approved: _t("Approved"),
    rejected: _t("Rejected"),
};
const RUN_STATES = {
    running: _t("Running"),
    waiting: _t("Waiting"),
    done: _t("Done"),
    failed: _t("Failed"),
    cancelled: _t("Cancelled"),
};
const TRIGGERS = [
    ["create", _t("A record is created")],
    ["change", _t("A record is created or updated")],
    ["date", _t("A date of the record comes")],
    ["manual", _t("Someone starts it from the Action menu")],
];
const POLICIES = [
    ["single", _t("One run at a time per record")],
    ["once", _t("Only once per record, ever")],
    ["multiple", _t("A new run every time")],
];
const UNITS = [
    ["minutes", _t("minutes")],
    ["hours", _t("hours")],
    ["days", _t("days")],
    ["weeks", _t("weeks")],
    ["months", _t("months")],
];
const DIRECTIONS = [
    ["before", _t("before")],
    ["after", _t("after")],
];
const VALUE_MODES = [
    ["value", _t("Set to")],
    ["field", _t("Copy from")],
    ["today", _t("Today plus")],
    ["clear", _t("Clear")],
];
// the default settings of a new step of each type
const DEFAULT_CONFIG = {
    condition: () => ({ domain: "[]" }),
    wait: () => ({ mode: "duration", amount: 1, unit: "days", direction: "after" }),
    wait_until: () => ({ domain: "[]", timeout: true, amount: 7, unit: "days" }),
    approval: () => ({ assign: "user", title: "", note: "", timeout: false, amount: 2, unit: "days",
                       lock: true, lock_mode: "fields", lock_fields: [], approver_only: false }),
    update: () => ({ values: [] }),
    create: () => ({ model: false, model_id: false, values: [], link_field: false }),
    email: () => ({ template_id: false }),
    activity: () => ({ activity_type_id: false, summary: "", note: "", assign: "user", days: 0 }),
    note: () => ({ body: "", message: false }),
    end: () => ({}),
};

let lastId = 0;
function newId(prefix) {
    lastId += 1;
    return `${prefix}${Date.now().toString(36)}${lastId}`;
}

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

function snap(value) {
    return Math.round(value / GRID) * GRID;
}

/** The exits of ``node``: the time limit one only when a limit is set. */
export function portsOf(node) {
    const ports = NODE_TYPES[node.type]?.ports || [];
    return ports.filter((port) => port !== "timeout" || node.config?.timeout);
}

export function nodeHeight(node) {
    const ports = portsOf(node).length;
    return ports > 1 ? HEAD_H + ports * PORT_GAP + 6 : NODE_H;
}

export function portPoint(node, port) {
    const ports = portsOf(node);
    const index = ports.indexOf(port);
    if (ports.length === 1) {
        return { x: node.x + NODE_W, y: node.y + NODE_H / 2 };
    }
    return { x: node.x + NODE_W, y: node.y + HEAD_H + PORT_GAP * index + PORT_GAP / 2 };
}

export function inPoint(node) {
    // the arrow head stops on the edge of the entry dot
    return { x: node.x - 8, y: node.y + NODE_H / 2 };
}

export function edgePath(from, to) {
    const dx = Math.max(40, Math.abs(to.x - from.x) / 2);
    return `M ${from.x} ${from.y} C ${from.x + dx} ${from.y}, ${to.x - dx} ${to.y}, ${to.x} ${to.y}`;
}

/**
 * The workflow designer: draw the steps of a workflow and the arrows between
 * them, set each step in the side panel, save and publish. With a run, the
 * same chart shows read-only the path the run took.
 */
export class WorkflowDesigner extends Component {
    static template = "om_automation_studio.Designer";
    static components = { DomainSelector, MultiRecordSelector, RecordSelector };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        const params = this.props.action.params || {};
        this.workflowId = params.workflow_id || this.props.action.context?.active_id;
        this.runId = params.run_id || false;

        this.NODE_TYPES = NODE_TYPES;
        this.PALETTE = PALETTE;
        this.PORT_LABELS = PORT_LABELS;
        this.RUN_STATES = RUN_STATES;
        this.TRIGGERS = TRIGGERS;
        this.POLICIES = POLICIES;
        this.UNITS = UNITS;
        this.DIRECTIONS = DIRECTIONS;
        this.VALUE_MODES = VALUE_MODES;
        this.NODE_W = NODE_W;
        this.portsOf = portsOf;

        this.state = useState({
            loaded: false,
            workflow: {},
            graph: { nodes: [], edges: [] },
            fields: [],
            targetFields: {},
            issues: [],
            selection: null,
            zoom: 1,
            pan: { x: 40, y: 40 },
            link: null,
            paletteGhost: null,
            dirty: false,
            saving: false,
            undoCount: 0,
            redoCount: 0,
            run: null,
            steps: [],
        });
        this.undoStack = [];
        this.redoStack = [];
        this.drag = null;

        this.canvasRef = useRef("canvas");
        useExternalListener(document, "pointermove", (ev) => this.onPointerMove(ev));
        useExternalListener(document, "pointerup", (ev) => this.onPointerUp(ev));
        useExternalListener(document, "keydown", (ev) => this.onKeyDown(ev));
        // not passive: a wheel with Ctrl zooms the chart instead of the page
        const onWheel = (ev) => this.onWheel(ev);
        onMounted(() => this.canvasRef.el?.addEventListener("wheel", onWheel, { passive: false }));
        onWillUnmount(() => this.canvasRef.el?.removeEventListener("wheel", onWheel));
        useExternalListener(window, "beforeunload", (ev) => {
            if (this.state.dirty) {
                ev.preventDefault();
                ev.returnValue = "";
            }
        });
        onWillStart(() => this.load());
        // on opening, stay readable: a wide chart starts at its left end
        onMounted(() => this.fit(0.75));
    }

    // ------------------------------------------------------------------
    // loading
    // ------------------------------------------------------------------

    async load() {
        if (this.runId) {
            const data = await this.orm.call(MODEL, "designer_run", [[this.workflowId], this.runId]);
            this.state.workflow = data.workflow;
            this.state.graph = data.graph || { nodes: [], edges: [] };
            this.state.run = data.run;
            this.state.steps = data.steps;
            this.state.selection = data.run.node ? { kind: "node", id: data.run.node } : null;
        } else {
            const data = await this.orm.call(MODEL, "designer_load", [[this.workflowId]]);
            this.state.workflow = data.workflow;
            this.state.graph = data.graph;
            this.state.fields = data.fields;
            this.state.issues = data.issues;
            for (const node of data.graph.nodes) {
                if (node.type === "create" && node.config.model) {
                    await this.loadTargetFields(node.config.model);
                }
            }
        }
        this.state.loaded = true;
    }

    async loadTargetFields(model) {
        if (model && !this.state.targetFields[model]) {
            this.state.targetFields[model] = await this.orm.call(MODEL, "designer_fields", [model]);
        }
    }

    readonly() {
        return Boolean(this.runId);
    }

    // ------------------------------------------------------------------
    // graph helpers
    // ------------------------------------------------------------------

    nodeById(id) {
        return this.state.graph.nodes.find((node) => node.id === id);
    }

    selectedNode() {
        const selection = this.state.selection;
        return selection?.kind === "node" ? this.nodeById(selection.id) : null;
    }

    isSelected(kind, id) {
        return this.state.selection?.kind === kind && this.state.selection.id === id;
    }

    nodeLabel(node) {
        return node.label || NODE_TYPES[node.type]?.label || node.type;
    }

    nodeSummary(node) {
        const config = node.config || {};
        switch (node.type) {
            case "start":
                return TRIGGERS.find(([key]) => key === config.trigger)?.[1] || "";
            case "wait":
                if (config.mode === "date") {
                    const field = this.fieldOf(config.date_field);
                    return field ? `${config.amount || 0} ${this.unitLabel(config.unit)} ${this.directionLabel(config.direction)} ${field.string}` : "";
                }
                return `${config.amount || 0} ${this.unitLabel(config.unit)}`;
            case "wait_until":
            case "approval":
                return config.timeout ? _t("at most %(amount)s %(unit)s", { amount: config.amount, unit: this.unitLabel(config.unit) }) : "";
            case "update":
                return (config.values || []).map((row) => this.fieldOf(row.field)?.string).filter(Boolean).join(", ");
            case "note":
            case "activity":
                return (config.summary || config.body || "").slice(0, 40);
            default:
                return "";
        }
    }

    unitLabel(unit) {
        return UNITS.find(([key]) => key === unit)?.[1] || "";
    }

    directionLabel(direction) {
        return DIRECTIONS.find(([key]) => key === direction)?.[1] || "";
    }

    fieldOf(name, fields = this.state.fields) {
        return fields.find((field) => field.name === name);
    }

    nodeIssues(node) {
        return this.state.issues.filter((issue) => issue.node === node.id);
    }

    globalIssues() {
        return this.state.issues.filter((issue) => !issue.node);
    }

    errorCount() {
        return this.state.issues.filter((issue) => issue.level === "error").length;
    }

    nodeClass(node) {
        const classes = [`o_om_wd_type_${node.type}`, this.nodeRunState(node)];
        if (this.isSelected("node", node.id)) {
            classes.push("o_om_wd_selected");
        }
        if (!this.state.run && this.nodeIssues(node).some((issue) => issue.level === "error")) {
            classes.push("o_om_wd_has_error");
        }
        const run = this.state.run;
        if (run && run.node === node.id && ["waiting", "failed"].includes(run.state)) {
            classes.push("o_om_wd_current");
        }
        return classes.join(" ");
    }

    nodeStyle(node) {
        return `left:${node.x}px;top:${node.y}px;width:${NODE_W}px;height:${nodeHeight(node)}px;`;
    }

    portStyle(node, port) {
        const point = portPoint(node, port);
        return `top:${point.y - node.y}px;`;
    }

    edgeD(edge) {
        const source = this.nodeById(edge.source);
        const target = this.nodeById(edge.target);
        if (!source || !target || !portsOf(source).includes(edge.port)) {
            return "";
        }
        return edgePath(portPoint(source, edge.port), inPoint(target));
    }

    linkD() {
        const link = this.state.link;
        const source = this.nodeById(link.source);
        return edgePath(portPoint(source, link.port), { x: link.x, y: link.y });
    }

    viewportStyle() {
        const { pan, zoom } = this.state;
        return `transform: translate(${pan.x}px, ${pan.y}px) scale(${zoom});`;
    }

    gridStyle() {
        const { pan, zoom } = this.state;
        const size = GRID * zoom;
        return `background-size:${size}px ${size}px;background-position:${pan.x}px ${pan.y}px;`;
    }

    // ------------------------------------------------------------------
    // run viewer
    // ------------------------------------------------------------------

    nodeRunState(node) {
        if (!this.state.run) {
            return "";
        }
        const steps = this.state.steps.filter((step) => step.node === node.id);
        if (!steps.length) {
            return "o_om_wd_unvisited";
        }
        const last = steps[steps.length - 1];
        return `o_om_wd_visited o_om_wd_step_${last.state}`;
    }

    edgeTaken(edge) {
        const steps = this.state.steps;
        return steps.some((step, index) => step.node === edge.source && step.port === edge.port
            && steps[index + 1]?.node === edge.target);
    }

    localDate(value) {
        return value ? formatDateTime(deserializeDateTime(value)) : "";
    }

    nodeSteps(node) {
        return this.state.steps.filter((step) => step.node === node.id);
    }

    // ------------------------------------------------------------------
    // history
    // ------------------------------------------------------------------

    remember() {
        this.undoStack.push(JSON.stringify(this.state.graph));
        if (this.undoStack.length > HISTORY_SIZE) {
            this.undoStack.shift();
        }
        this.redoStack = [];
        this.state.undoCount = this.undoStack.length;
        this.state.redoCount = 0;
        this.state.dirty = true;
    }

    undo() {
        if (!this.undoStack.length) {
            return;
        }
        this.redoStack.push(JSON.stringify(this.state.graph));
        this.state.graph = JSON.parse(this.undoStack.pop());
        this.afterHistory();
    }

    redo() {
        if (!this.redoStack.length) {
            return;
        }
        this.undoStack.push(JSON.stringify(this.state.graph));
        this.state.graph = JSON.parse(this.redoStack.pop());
        this.afterHistory();
    }

    afterHistory() {
        this.state.undoCount = this.undoStack.length;
        this.state.redoCount = this.redoStack.length;
        this.state.dirty = true;
        if (this.state.selection && !this.nodeById(this.state.selection.id)
            && !this.state.graph.edges.find((edge) => edge.id === this.state.selection.id)) {
            this.state.selection = null;
        }
    }

    // ------------------------------------------------------------------
    // editing
    // ------------------------------------------------------------------

    addNode(type, x, y) {
        if (this.readonly()) {
            return;
        }
        this.remember();
        const node = {
            id: newId("n"),
            type,
            x: snap(x),
            y: snap(y),
            label: "",
            config: DEFAULT_CONFIG[type](),
        };
        // a new step goes after the selected one, on its first free exit
        const previous = this.selectedNode();
        if (previous && x === undefined) {
            node.x = previous.x + NODE_W + 80;
            node.y = previous.y;
            const freePort = portsOf(previous).find((port) =>
                !this.state.graph.edges.find((edge) => edge.source === previous.id && edge.port === port));
            const replaced = this.state.graph.edges.find((edge) => edge.source === previous.id
                && edge.port === (freePort || portsOf(previous)[0]));
            if (NODE_TYPES[type].ports.length && replaced && !freePort) {
                // insert the step on the arrow
                this.state.graph.edges.push({ id: newId("e"), source: node.id, port: NODE_TYPES[type].ports[0], target: replaced.target });
                replaced.target = node.id;
                this.shiftRight(previous.x + NODE_W, node.id);
            } else if (freePort) {
                this.state.graph.edges.push({ id: newId("e"), source: previous.id, port: freePort, target: node.id });
            }
        } else if (x === undefined) {
            const canvas = this.canvasRef.el;
            const rect = canvas.getBoundingClientRect();
            node.x = snap((rect.width / 2 - this.state.pan.x) / this.state.zoom - NODE_W / 2);
            node.y = snap((rect.height / 2 - this.state.pan.y) / this.state.zoom - NODE_H / 2);
        }
        this.state.graph.nodes.push(node);
        this.state.selection = { kind: "node", id: node.id };
    }

    /** Make room for an inserted step: move what is on the right of ``fromX``. */
    shiftRight(fromX, exceptId) {
        for (const node of this.state.graph.nodes) {
            if (node.id !== exceptId && node.x >= fromX) {
                node.x += NODE_W + 80;
            }
        }
    }

    removeSelection() {
        const selection = this.state.selection;
        if (!selection || this.readonly()) {
            return;
        }
        const graph = this.state.graph;
        if (selection.kind === "node") {
            const node = this.nodeById(selection.id);
            if (!node || node.type === "start") {
                return;
            }
            this.remember();
            // keep the chain: what led to the step now leads to where its first exit went
            const incoming = graph.edges.filter((edge) => edge.target === node.id);
            const outgoing = graph.edges.filter((edge) => edge.source === node.id);
            if (outgoing.length === 1) {
                for (const edge of incoming) {
                    edge.target = outgoing[0].target;
                }
                graph.edges = graph.edges.filter((edge) => edge.source !== node.id);
            } else {
                graph.edges = graph.edges.filter((edge) => edge.source !== node.id && edge.target !== node.id);
            }
            graph.nodes = graph.nodes.filter((n) => n.id !== node.id);
        } else {
            this.remember();
            graph.edges = graph.edges.filter((edge) => edge.id !== selection.id);
        }
        this.state.selection = null;
    }

    duplicateSelection() {
        const node = this.selectedNode();
        if (!node || node.type === "start" || this.readonly()) {
            return;
        }
        this.remember();
        const copy = { ...clone(node), id: newId("n"), x: node.x + GRID * 2, y: node.y + GRID * 4 };
        this.state.graph.nodes.push(copy);
        this.state.selection = { kind: "node", id: copy.id };
    }

    connect(source, port, target) {
        if (source === target || this.nodeById(target)?.type === "start") {
            return;
        }
        this.remember();
        const graph = this.state.graph;
        graph.edges = graph.edges.filter((edge) => !(edge.source === source && edge.port === port));
        graph.edges.push({ id: newId("e"), source, port, target });
    }

    setLabel(node, value) {
        this.remember();
        node.label = value;
    }

    setConfig(node, key, value) {
        if (this.readonly()) {
            return;
        }
        this.remember();
        node.config[key] = value;
        if (key === "timeout" && !value) {
            // no limit: no time limit exit, nor its arrow
            this.state.graph.edges = this.state.graph.edges.filter(
                (edge) => !(edge.source === node.id && edge.port === "timeout"));
        }
    }

    // ------------------------------------------------------------------
    // pointer
    // ------------------------------------------------------------------

    toCanvas(ev) {
        const rect = this.canvasRef.el.getBoundingClientRect();
        return {
            x: (ev.clientX - rect.left - this.state.pan.x) / this.state.zoom,
            y: (ev.clientY - rect.top - this.state.pan.y) / this.state.zoom,
        };
    }

    onCanvasPointerDown(ev) {
        if (ev.button !== 0) {
            return;
        }
        this.drag = { kind: "pan", startX: ev.clientX, startY: ev.clientY, pan: { ...this.state.pan }, moved: false };
    }

    onNodePointerDown(ev, node) {
        if (ev.button !== 0) {
            return;
        }
        ev.stopPropagation();
        this.state.selection = { kind: "node", id: node.id };
        if (this.readonly()) {
            return;
        }
        const point = this.toCanvas(ev);
        this.drag = { kind: "node", id: node.id, dx: point.x - node.x, dy: point.y - node.y,
                      startX: ev.clientX, startY: ev.clientY, moved: false };
    }

    onPortPointerDown(ev, node, port) {
        ev.stopPropagation();
        if (this.readonly()) {
            return;
        }
        const point = this.toCanvas(ev);
        this.state.link = { source: node.id, port, x: point.x, y: point.y };
        this.drag = { kind: "link" };
    }

    onPalettePointerDown(ev, type) {
        if (ev.button !== 0) {
            return;
        }
        this.drag = { kind: "palette", type, startX: ev.clientX, startY: ev.clientY, moved: false };
    }

    onEdgePointerDown(ev, edge) {
        ev.stopPropagation();
        this.state.selection = { kind: "edge", id: edge.id };
    }

    onPointerMove(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        if (drag.startX !== undefined && !drag.moved) {
            drag.moved = Math.abs(ev.clientX - drag.startX) + Math.abs(ev.clientY - drag.startY) > DRAG_THRESHOLD_PX;
            if (drag.moved && drag.kind === "node") {
                this.remember();
            }
            if (!drag.moved) {
                return;
            }
        }
        if (drag.kind === "pan") {
            this.state.pan.x = drag.pan.x + ev.clientX - drag.startX;
            this.state.pan.y = drag.pan.y + ev.clientY - drag.startY;
        } else if (drag.kind === "node") {
            const node = this.nodeById(drag.id);
            const point = this.toCanvas(ev);
            node.x = snap(point.x - drag.dx);
            node.y = snap(point.y - drag.dy);
        } else if (drag.kind === "link") {
            const point = this.toCanvas(ev);
            this.state.link.x = point.x;
            this.state.link.y = point.y;
        } else if (drag.kind === "palette") {
            this.state.paletteGhost = { type: drag.type, x: ev.clientX, y: ev.clientY };
        }
    }

    onPointerUp(ev) {
        const drag = this.drag;
        this.drag = null;
        if (!drag) {
            return;
        }
        if (drag.kind === "pan" && !drag.moved) {
            this.state.selection = null;
        } else if (drag.kind === "link") {
            const target = ev.target.closest?.("[data-node-id]");
            const link = this.state.link;
            this.state.link = null;
            if (target) {
                this.connect(link.source, link.port, target.dataset.nodeId);
            }
        } else if (drag.kind === "palette") {
            this.state.paletteGhost = null;
            const canvas = this.canvasRef.el;
            const rect = canvas.getBoundingClientRect();
            const inside = ev.clientX >= rect.left && ev.clientX <= rect.right
                && ev.clientY >= rect.top && ev.clientY <= rect.bottom;
            if (drag.moved && inside) {
                const point = this.toCanvas(ev);
                this.state.selection = null;
                this.addNode(drag.type, point.x - NODE_W / 2, point.y - NODE_H / 2);
            } else if (!drag.moved) {
                this.addNode(drag.type);
            }
        }
    }

    onWheel(ev) {
        ev.preventDefault();
        if (ev.ctrlKey || ev.metaKey) {
            const rect = this.canvasRef.el.getBoundingClientRect();
            const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
            this.zoomAt(this.state.zoom * factor, ev.clientX - rect.left, ev.clientY - rect.top);
        } else {
            this.state.pan.x -= ev.deltaX;
            this.state.pan.y -= ev.deltaY;
        }
    }

    zoomAt(value, cx, cy) {
        const zoom = Math.min(2, Math.max(0.3, value));
        const { pan } = this.state;
        pan.x = cx - ((cx - pan.x) * zoom) / this.state.zoom;
        pan.y = cy - ((cy - pan.y) * zoom) / this.state.zoom;
        this.state.zoom = zoom;
    }

    zoomBy(factor) {
        const rect = this.canvasRef.el.getBoundingClientRect();
        this.zoomAt(this.state.zoom * factor, rect.width / 2, rect.height / 2);
    }

    fit(minZoom = 0.3) {
        const nodes = this.state.graph.nodes;
        const canvas = this.canvasRef.el;
        if (!nodes.length || !canvas) {
            return;
        }
        const minX = Math.min(...nodes.map((n) => n.x));
        const minY = Math.min(...nodes.map((n) => n.y));
        const maxX = Math.max(...nodes.map((n) => n.x + NODE_W));
        const maxY = Math.max(...nodes.map((n) => n.y + nodeHeight(n)));
        const rect = canvas.getBoundingClientRect();
        const zoom = Math.min(1.2, Math.max(minZoom, Math.min((rect.width - 80) / (maxX - minX), (rect.height - 80) / (maxY - minY))));
        this.state.zoom = zoom;
        const width = (maxX - minX) * zoom;
        this.state.pan.x = width > rect.width - 80 ? 40 - minX * zoom : (rect.width - width) / 2 - minX * zoom;
        this.state.pan.y = (rect.height - (maxY - minY) * zoom) / 2 - minY * zoom;
    }

    onKeyDown(ev) {
        const tag = ev.target.tagName;
        const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || ev.target.isContentEditable;
        const mod = ev.ctrlKey || ev.metaKey;
        if (mod && ev.key.toLowerCase() === "s") {
            ev.preventDefault();
            this.save();
        } else if (typing) {
            return;
        } else if (mod && ev.key.toLowerCase() === "z") {
            ev.preventDefault();
            ev.shiftKey ? this.redo() : this.undo();
        } else if (mod && ev.key.toLowerCase() === "y") {
            ev.preventDefault();
            this.redo();
        } else if (mod && ev.key.toLowerCase() === "d") {
            ev.preventDefault();
            this.duplicateSelection();
        } else if (ev.key === "Delete" || ev.key === "Backspace") {
            this.removeSelection();
        } else if (ev.key === "Escape") {
            this.state.selection = null;
        }
    }

    // ------------------------------------------------------------------
    // side panel helpers
    // ------------------------------------------------------------------

    fieldsWhere(filter, fields = this.state.fields) {
        return fields.filter(filter);
    }

    dateFields(stored = false) {
        return this.fieldsWhere((f) => ["date", "datetime"].includes(f.type) && (!stored || f.store));
    }

    userFields() {
        return this.fieldsWhere((f) => f.type === "many2one" && f.relation === "res.users");
    }

    settableFields(fields) {
        return fields.filter((f) => f.settable && [
            "char", "text", "html", "integer", "float", "monetary", "boolean", "selection",
            "date", "datetime", "many2one", "many2many",
        ].includes(f.type));
    }

    valueFields(node) {
        if (node.type === "create") {
            return this.state.targetFields[node.config.model] || [];
        }
        return this.state.fields;
    }

    /** The fields of the record of the run a value can be copied from into ``field``. */
    sourceFields(field) {
        if (!field) {
            return [];
        }
        if (["many2one", "many2many"].includes(field.type)) {
            return this.fieldsWhere((f) => f.relation === field.relation && ["many2one", "many2many"].includes(f.type));
        }
        const compatible = {
            char: ["char", "text", "selection", "many2one"],
            text: ["char", "text", "html"],
            html: ["char", "text", "html"],
            integer: ["integer"],
            float: ["float", "monetary", "integer"],
            monetary: ["float", "monetary", "integer"],
            date: ["date", "datetime"],
            datetime: ["datetime", "date"],
        }[field.type] || [field.type];
        return this.fieldsWhere((f) => compatible.includes(f.type));
    }

    linkFields(node) {
        const model = this.state.workflow.model;
        return (this.state.targetFields[node.config.model] || []).filter(
            (f) => f.type === "many2one" && f.relation === model);
    }

    toggleWatched(node, name, checked, key = "fields") {
        const fields = new Set(node.config[key] || []);
        checked ? fields.add(name) : fields.delete(name);
        this.setConfig(node, key, [...fields]);
    }

    /** The fields an approval blocks when none is chosen: the status. */
    defaultLockLabel() {
        return this.fieldOf("state")?.string || "";
    }

    addValueRow(node) {
        this.remember();
        node.config.values = [...(node.config.values || []), { field: "", mode: "value", value: false }];
    }

    removeValueRow(node, index) {
        this.remember();
        node.config.values.splice(index, 1);
    }

    setRow(node, index, key, value) {
        this.remember();
        const row = node.config.values[index];
        row[key] = value;
        if (key === "field") {
            const field = this.fieldOf(value, this.valueFields(node));
            row.mode = "value";
            row.value = field?.type === "boolean" ? true : field?.type === "many2many" ? [] : false;
            row.source = "";
        }
        if (key === "mode") {
            row.offset = 0;
        }
    }

    rowModes(field) {
        return VALUE_MODES.filter(([mode]) => mode !== "today" || ["date", "datetime"].includes(field?.type));
    }

    async setTargetModel(node, modelId) {
        const model = modelId ? await this.orm.call(MODEL, "designer_model_name", [modelId]) : false;
        await this.loadTargetFields(model);
        this.remember();
        Object.assign(node.config, { model_id: modelId || false, model, values: [], link_field: false });
    }

    numberValue(ev) {
        const value = parseFloat(ev.target.value);
        return Number.isNaN(value) ? 0 : value;
    }

    // ------------------------------------------------------------------
    // server
    // ------------------------------------------------------------------

    async save() {
        if (this.readonly() || this.state.saving) {
            return false;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(MODEL, "designer_save", [[this.workflowId], clone(this.state.graph),
                this.state.workflow.name]);
            this.state.workflow = result.workflow;
            this.state.issues = result.issues;
            this.state.dirty = false;
            return true;
        } finally {
            this.state.saving = false;
        }
    }

    async publish() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(MODEL, "designer_publish", [[this.workflowId], clone(this.state.graph),
                this.state.workflow.name]);
            this.state.workflow = result.workflow;
            this.state.issues = result.issues;
            this.state.dirty = false;
            this.notification.add(_t("Published: version %s is running.", result.workflow.version), { type: "success" });
        } catch (error) {
            // the issues of the chart show what to fix
            const result = await this.orm.call(MODEL, "designer_save", [[this.workflowId], clone(this.state.graph),
                this.state.workflow.name]);
            this.state.workflow = result.workflow;
            this.state.issues = result.issues;
            this.state.dirty = false;
            throw error;
        } finally {
            this.state.saving = false;
        }
    }

    async pause() {
        const result = await this.orm.call(MODEL, "designer_pause", [[this.workflowId]]);
        this.state.workflow = result.workflow;
        this.notification.add(_t("Paused: no new run starts."), { type: "warning" });
    }

    setName(value) {
        this.state.workflow.name = value;
        this.state.dirty = true;
    }

    async saveAsTemplate() {
        if (this.state.dirty && !(await this.save())) {
            return;
        }
        const action = await this.orm.call(MODEL, "action_save_as_template", [[this.workflowId]]);
        await this.action.doAction(action);
    }

    openRuns() {
        this.leave(() => this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Runs"),
            res_model: "om.workflow.run",
            views: [[false, "list"], [false, "form"]],
            domain: [["workflow_id", "=", this.workflowId]],
            context: { search_default_open: 1 },
        }));
    }

    openRecord() {
        this.action.doActionButton({
            type: "object",
            name: "action_open_record",
            resModel: "om.workflow.run",
            resId: this.runId,
        });
    }

    openDesigner() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "om_automation_studio",
            name: this.state.workflow.name,
            params: { workflow_id: this.workflowId },
        });
    }

    close() {
        this.leave(() => this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.runId ? "om.workflow.run" : MODEL,
            res_id: this.runId || this.workflowId,
            views: [[false, "form"]],
        }));
    }

    leave(callback) {
        if (!this.state.dirty) {
            callback();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Unsaved Changes"),
            body: _t("Save the changes to the workflow before leaving?"),
            confirmLabel: _t("Save"),
            confirm: async () => {
                if (await this.save()) {
                    callback();
                }
            },
            cancelLabel: _t("Discard"),
            cancel: () => {
                this.state.dirty = false;
                callback();
            },
        });
    }
}

registry.category("actions").add("om_automation_studio", WorkflowDesigner);
