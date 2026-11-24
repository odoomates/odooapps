import { Component, onMounted, onWillUnmount, proxy, signal, useListener, useProps } from "@odoo/owl";
import { View } from "@web/views/view";
import { SearchEditor } from "./search_editor";

const NODE_RE = /\bo_pen_n(\d+)\b/;
const DRAG_THRESHOLD = 5;

/** The node id carried by `el` or its closest numbered ancestor inside `root`. */
export function nodeIdOf(el, root, store) {
    while (el && el !== root && el.nodeType === 1) {
        const classes = typeof el.className === "string" ? el.className : el.getAttribute("class") || "";
        const match = classes.match(NODE_RE);
        if (match) {
            return Number(match[1]);
        }
        // the label cell of a field in a group carries no class of the arch: go to
        // the field it labels
        const label = el.tagName === "LABEL" ? el : el.classList?.contains("o_wrap_label") ? el.querySelector("label[for]") : null;
        if (label?.htmlFor) {
            const input = root.querySelector(`#${CSS.escape(label.htmlFor)}`);
            if (input && input !== el) {
                const id = nodeIdOf(input, root, store);
                if (id !== null) {
                    return id;
                }
            }
        }
        // notebook tabs and list headers are found by name
        if (el.matches?.(".nav-link[name]")) {
            const id = store.findNode((n) => n.tag === "page" && n.attrs.name === el.getAttribute("name"));
            if (id !== null) {
                return id;
            }
        }
        if (el.matches?.("th[data-name]") && !el.closest(".o_field_x2many")) {
            const id = store.findNode(
                (n) => n.tag === "field" && !n.owners.length && n.attrs.name === el.dataset.name
            );
            if (id !== null) {
                return id;
            }
        }
        el = el.parentElement;
    }
    return null;
}

/** Tags that are placed before or after, side by side when they are list columns. */
const SIBLING_TAGS = ["field", "separator", "button", "label", "div", "widget", "notebook", "group", "span", "a", "img", "h1", "h2", "h3", "p"];
const CONTAINER_TAGS = ["group", "page", "sheet", "div", "main", "aside", "footer", "header", "list", "kanban", "form"];

export class StudioCanvas extends Component {
    static template = "om_pen.StudioCanvas";
    static components = { View, SearchEditor };
    props = useProps();

    rootRef = signal.ref();

    setup() {
        this.store = this.props.store;
        this.ui = proxy({ indicator: null });
        this.pointer = null; // mousedown on a node of the canvas
        this.justDragged = false;

        useListener(this.rootRef, "click", (ev) => this.onClick(ev), { capture: true });
        useListener(this.rootRef, "mousedown", (ev) => this.onMouseDown(ev), { capture: true });
        useListener(this.rootRef, "dblclick", (ev) => this.stop(ev), { capture: true });
        useListener(this.rootRef, "keydown", (ev) => this.stop(ev), { capture: true });
        useListener(this.rootRef, "mouseover", (ev) => this.onHover(ev));
        useListener(this.rootRef, "mouseleave", () => this.hover(null));
        useListener(document, "mousemove", (ev) => this.onMouseMove(ev));
        useListener(document, "mouseup", (ev) => this.onMouseUp(ev));

        onMounted(() => {
            // the view renders asynchronously and re-renders on its own: mark the
            // selection again whenever its DOM changes
            this.observer = new MutationObserver(() => this.markSelection());
            this.observer.observe(this.rootRef(), { childList: true, subtree: true });
            this.markSelection();
        });
        onWillUnmount(() => this.observer?.disconnect());
    }

    /**
     * The props of the View, built once per draft. A new object on every render
     * would make the View load its record again on every mouse move of a drag.
     */
    get viewProps() {
        const key = this.store.state.canvasKey;
        if (this._viewProps?.key !== key) {
            this._viewProps = { key, props: this.buildViewProps() };
        }
        return this._viewProps.props;
    }

    buildViewProps() {
        const view = this.store.view;
        const props = {
            type: view.view_type,
            resModel: view.model,
            arch: view.arch,
            fields: view.fields,
            relatedModels: view.related_models,
            context: { om_pen_studio: true },
            domain: [],
            display: { controlPanel: false, searchPanel: false },
            className: "o_pen_canvas_view",
            useSampleModel: !["form"].includes(view.view_type),
        };
        if (view.view_type === "form") {
            // the smart buttons of a form are drawn in its control panel
            props.display = { controlPanel: {}, searchPanel: false };
            props.resId = this.store.state.resId || this.props.firstResId || false;
            props.preventEdit = false;
        }
        return props;
    }

    get isSearch() {
        return this.store.view?.view_type === "search";
    }

    stop(ev) {
        ev.stopPropagation();
        ev.preventDefault();
    }

    // ------------------------------------------------------------------
    // selection
    // ------------------------------------------------------------------

    onClick(ev) {
        if (this.isSearch) {
            return;
        }
        this.stop(ev);
        if (this.justDragged) {
            this.justDragged = false;
            return;
        }
        const id = nodeIdOf(ev.target, this.rootRef(), this.store);
        this.store.select(id);
        this.markSelection();
    }

    onHover(ev) {
        if (this.isSearch || this.store.state.drag) {
            return;
        }
        this.hover(nodeIdOf(ev.target, this.rootRef(), this.store));
    }

    hover(id) {
        const root = this.rootRef();
        if (!root) {
            return;
        }
        for (const el of root.querySelectorAll(".o_pen_hover")) {
            el.classList.remove("o_pen_hover");
        }
        if (id !== null) {
            for (const el of this.elementsOf(id)) {
                el.classList.add("o_pen_hover");
            }
        }
    }

    elementsOf(id) {
        const root = this.rootRef();
        if (!root || id === null || id === undefined) {
            return [];
        }
        const elements = [...root.querySelectorAll(`.o_pen_n${id}`)];
        const node = this.store.node(id);
        if (node?.tag === "page" && node.attrs.name) {
            elements.push(...root.querySelectorAll(`.nav-link[name="${CSS.escape(node.attrs.name)}"]`));
        }
        if (node?.tag === "field" && !node.owners.length && this.store.view.view_type === "list") {
            elements.push(...root.querySelectorAll(`th[data-name="${CSS.escape(node.attrs.name)}"]`));
        }
        return elements;
    }

    markSelection() {
        const root = this.rootRef();
        if (!root) {
            return;
        }
        const selected = this.store.state.selected;
        const wanted = new Set(this.elementsOf(selected));
        for (const el of root.querySelectorAll(".o_pen_selected")) {
            if (!wanted.has(el)) {
                el.classList.remove("o_pen_selected");
            }
        }
        for (const el of wanted) {
            if (!el.classList.contains("o_pen_selected")) {
                el.classList.add("o_pen_selected");
            }
        }
    }

    // ------------------------------------------------------------------
    // dragging
    // ------------------------------------------------------------------

    onMouseDown(ev) {
        if (this.isSearch || ev.button !== 0) {
            return;
        }
        this.stop(ev);
        const id = nodeIdOf(ev.target, this.rootRef(), this.store);
        const node = this.store.node(id);
        if (node && id !== this.store.rootId && ["field", "group", "page", "button", "separator", "notebook", "widget", "label", "div"].includes(node.tag)) {
            this.pointer = { id, x: ev.clientX, y: ev.clientY };
        }
    }

    onMouseMove(ev) {
        if (this.pointer && !this.store.state.drag) {
            const distance = Math.abs(ev.clientX - this.pointer.x) + Math.abs(ev.clientY - this.pointer.y);
            if (distance > DRAG_THRESHOLD) {
                const node = this.store.node(this.pointer.id);
                this.store.state.drag = {
                    kind: "move",
                    node: this.pointer.id,
                    tag: node.tag,
                    label: this.store.labelOf(node),
                    model: node.model,
                };
            }
        }
        const drag = this.store.state.drag;
        if (!drag) {
            return;
        }
        this.store.state.dragPos = { x: ev.clientX, y: ev.clientY };
        this.ui.indicator = this.dropTarget(ev, drag);
    }

    async onMouseUp(ev) {
        const drag = this.store.state.drag;
        const pointer = this.pointer;
        this.pointer = null;
        if (!drag) {
            return;
        }
        this.store.state.drag = null;
        const target = this.ui.indicator;
        this.ui.indicator = null;
        if (pointer) {
            this.justDragged = true;
        }
        if (!target) {
            return;
        }
        await this.props.onDrop(drag, target.id, target.position);
    }

    /** Where the dragged thing would land: { id, position, rect } or null. */
    dropTarget(ev, drag) {
        const root = this.rootRef();
        if (!root) {
            return null;
        }
        const el = document.elementFromPoint(ev.clientX, ev.clientY);
        if (!el || !root.contains(el)) {
            return null;
        }
        const viewType = this.store.view.view_type;
        let id = nodeIdOf(el, root, this.store);
        const seen = new Set();
        while (id !== null && id !== undefined && !seen.has(id)) {
            seen.add(id);
            const node = this.store.node(id);
            if (!node) {
                return null;
            }
            const found = this.accept(node, drag, viewType, ev);
            if (found) {
                return found;
            }
            id = node.parent;
        }
        return null;
    }

    accept(node, drag, viewType, ev) {
        if (!node || (drag.kind === "move" && node.id === drag.node)) {
            return null;
        }
        if (drag.kind === "move" && this.isInside(node.id, drag.node)) {
            return null;
        }
        if (drag.model && node.model !== drag.model && !(node.tag === "field" && node.relation === drag.model && node.subviews?.length)) {
            // a field only goes on a view of its own model
            if (node.tag !== "list" && node.tag !== "form") {
                return null;
            }
        }
        const isPage = drag.tag === "page" || drag.element?.kind === "page";
        const rect = this.rectOf(node.id);
        if (!rect) {
            return null;
        }
        if (isPage) {
            if (node.tag === "notebook") {
                return { id: node.id, position: "inside", rect, mode: "box" };
            }
            if (node.tag === "page") {
                return { id: node.id, position: "after", rect, mode: "box" };
            }
            return null;
        }
        if (node.tag === "page" && drag.tag !== "page") {
            return { id: node.id, position: "inside", rect, mode: "box" };
        }
        const columns = viewType === "list" || (node.owners?.length && this.inList(node.id));
        if (node.tag === "field" && node.parent !== null && this.store.node(node.parent)?.tag === "header") {
            return null;
        }
        if (SIBLING_TAGS.includes(node.tag) && node.id !== this.store.rootId) {
            const parent = this.store.node(node.parent);
            if (node.tag === "group" && parent?.tag === "group" && !this.hasFields(node.id)) {
                return { id: node.id, position: "inside", rect, mode: "box" };
            }
            if (node.tag === "group" && this.nearBottom(rect, ev)) {
                return { id: node.id, position: "inside", rect, mode: "box" };
            }
            if (columns) {
                const after = ev.clientX > rect.left + rect.width / 2;
                return { id: node.id, position: after ? "after" : "before", rect, mode: "vertical" };
            }
            const after = ev.clientY > rect.top + rect.height / 2;
            return { id: node.id, position: after ? "after" : "before", rect, mode: "horizontal" };
        }
        if (CONTAINER_TAGS.includes(node.tag) && !(viewType === "kanban" && node.tag === "kanban")) {
            return { id: node.id, position: "inside", rect, mode: "box" };
        }
        return null;
    }

    isInside(id, ancestor) {
        let node = this.store.node(id);
        const seen = new Set();
        while (node && !seen.has(node.id)) {
            seen.add(node.id);
            if (node.id === ancestor) {
                return true;
            }
            node = this.store.node(node.parent);
        }
        return false;
    }

    inList(id) {
        let node = this.store.node(id);
        const seen = new Set();
        while (node && !seen.has(node.id)) {
            seen.add(node.id);
            if (node.tag === "list") {
                return true;
            }
            if (node.tag === "form") {
                return false;
            }
            node = this.store.node(node.parent);
        }
        return false;
    }

    hasFields(id) {
        return Object.values(this.store.nodes).some((n) => n.parent === id);
    }

    nearBottom(rect, ev) {
        return ev.clientY > rect.bottom - 14;
    }

    rectOf(id) {
        const elements = this.elementsOf(id).filter((el) => el.offsetParent !== null);
        if (!elements.length) {
            return null;
        }
        const rects = elements.map((el) => el.getBoundingClientRect());
        const left = Math.min(...rects.map((r) => r.left));
        const top = Math.min(...rects.map((r) => r.top));
        const right = Math.max(...rects.map((r) => r.right));
        const bottom = Math.max(...rects.map((r) => r.bottom));
        return { left, top, right, bottom, width: right - left, height: bottom - top };
    }

    get indicatorStyle() {
        const target = this.ui.indicator;
        const root = this.rootRef();
        if (!target || !root) {
            return "display: none";
        }
        const base = root.getBoundingClientRect();
        const { rect, position, mode } = target;
        const left = rect.left - base.left + root.scrollLeft;
        const top = rect.top - base.top + root.scrollTop;
        if (mode === "box") {
            return `left: ${left}px; top: ${top}px; width: ${rect.width}px; height: ${rect.height}px;`;
        }
        if (mode === "vertical") {
            const x = position === "after" ? left + rect.width : left;
            return `left: ${x - 2}px; top: ${top}px; width: 4px; height: ${Math.max(rect.height, 24)}px;`;
        }
        const y = position === "after" ? top + rect.height : top;
        return `left: ${left}px; top: ${y - 2}px; width: ${rect.width}px; height: 4px;`;
    }

    get indicatorClass() {
        const target = this.ui.indicator;
        return target?.mode === "box" ? "o_pen_drop_box" : "o_pen_drop_line";
    }
}
