import { markRaw, proxy } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export const TAG_LABELS = {
    form: _t("Form"),
    list: _t("List"),
    kanban: _t("Kanban"),
    group: _t("Group"),
    page: _t("Tab"),
    notebook: _t("Tabs"),
    separator: _t("Section"),
    button: _t("Button"),
    widget: _t("Widget"),
    label: _t("Label"),
    div: _t("Block"),
    sheet: _t("Sheet"),
    header: _t("Header"),
    chatter: _t("Chatter"),
    filter: _t("Filter"),
    search: _t("Search"),
};

/**
 * State of the Studio, shared by the shell, the canvas and the side panel.
 *
 * Every change goes to the server, which answers with the whole draft view again:
 * the canvas always shows exactly what would be published, numbered afresh.
 */
export class StudioStore {
    constructor({ orm, notification }) {
        this.orm = orm;
        this.notification = notification;
        this.state = proxy({
            info: null, // studio_open: model, view type, action, customization
            view: null, // studio_view: arch, fields, nodes, history...
            selected: null, // node id
            tab: "add", // add | properties | view
            section: "views", // top bar section
            showHidden: false,
            busy: false,
            resId: false,
            drag: null, // { kind, payload, label } while dragging from the panel
            canvasKey: 0, // bumped to force the canvas to render afresh
        });
    }

    get info() {
        return this.state.info;
    }

    get view() {
        return this.state.view;
    }

    get nodes() {
        return this.state.view?.nodes || {};
    }

    node(id) {
        return id === null || id === undefined ? null : this.nodes[id] || null;
    }

    findNode(predicate) {
        for (const node of Object.values(this.nodes)) {
            if (predicate(node)) {
                return node.id;
            }
        }
        return null;
    }

    /** What a node is called in the panel and in the history. */
    labelOf(node) {
        if (!node) {
            return "";
        }
        if (node.tag === "field") {
            return node.attrs.string || node.field_string || node.attrs.name;
        }
        const caption = node.attrs.string || node.attrs.title || node.attrs.name || node.text || "";
        return caption ? `${TAG_LABELS[node.tag] || node.tag}: ${caption}` : TAG_LABELS[node.tag] || node.tag;
    }

    get selectedNode() {
        return this.node(this.state.selected);
    }

    get rootId() {
        const ids = Object.keys(this.nodes).map(Number);
        return ids.length ? Math.min(...ids) : null;
    }

    /** The model whose fields the Add tab offers: the one of the selected node. */
    get focusModel() {
        const node = this.selectedNode;
        if (!node) {
            return this.info?.model;
        }
        if (node.tag === "field" && node.relation && node.subviews?.length) {
            return node.relation;
        }
        return node.model || this.info?.model;
    }

    async open(params) {
        this.state.info = await this.orm.call("om.pen.studio", "studio_open", [
            params.model,
            params.viewType || "form",
            params.viewId || false,
            params.actionId || false,
        ]);
        if (params.resId) {
            this.state.resId = params.resId;
        }
        await this.reload();
    }

    async switchView(viewType) {
        const info = this.state.info;
        this.state.selected = null;
        this.state.tab = "add";
        await this.open({
            model: info.model,
            viewType,
            actionId: info.action?.id,
            resId: this.state.resId,
        });
    }

    async reload() {
        await this._run("studio_view", [this.state.info.customization_id, this.state.showHidden]);
    }

    setView(view) {
        // the arch and fields are handed to the View as they are: nothing reactive
        view.fields = markRaw(view.fields);
        view.related_models = markRaw(view.related_models);
        this.state.view = view;
        this.state.canvasKey++;
        if (this.state.selected !== null && !view.nodes[this.state.selected]) {
            this.state.selected = null;
        }
    }

    select(id) {
        this.state.selected = id;
        if (id !== null) {
            this.state.tab = "properties";
        }
    }

    /** Apply one or several changes as one step. */
    async change(changes) {
        const view = this.state.view;
        return this._run("studio_change", [
            this.state.info.customization_id,
            view.revision,
            changes,
            this.state.showHidden,
        ]);
    }

    async setAttrs(nodeId, values) {
        return this.change({ op: "attrs", node: nodeId, values });
    }

    async remove(nodeId) {
        const done = await this.change({ op: "remove", node: nodeId });
        if (done) {
            this.state.selected = null;
            this.state.tab = "add";
        }
        return done;
    }

    async move(nodeId, target, position) {
        return this.change({ op: "move", node: nodeId, target, position });
    }

    async insert(target, position, element) {
        return this.change({ op: "insert", target, position, element });
    }

    async call(method, args) {
        return this._run(method, [this.state.info.customization_id, ...args]);
    }

    async undo() {
        return this._run("studio_undo", [this.state.info.customization_id, this.state.showHidden]);
    }

    async redo() {
        return this._run("studio_redo", [this.state.info.customization_id, this.state.showHidden]);
    }

    async publish() {
        const done = await this._run("studio_publish", [
            this.state.info.customization_id,
            this.state.showHidden,
        ]);
        if (done) {
            this.notification.add(_t("Published: everybody sees these changes now."), {
                type: "success",
            });
        }
        return done;
    }

    async discard() {
        return this._run("studio_discard", [this.state.info.customization_id, this.state.showHidden]);
    }

    async reset() {
        return this._run("studio_reset", [this.state.info.customization_id, this.state.showHidden]);
    }

    async toggleHidden() {
        this.state.showHidden = !this.state.showHidden;
        await this.reload();
    }

    /** Run a server method answering with the view, and show it. */
    async _run(method, args) {
        this.state.busy = true;
        try {
            const view = await this.orm.call("om.pen.studio", method, args);
            this.setView(view);
            return true;
        } catch (error) {
            this.state.busy = false;
            throw error;
        } finally {
            this.state.busy = false;
        }
    }
}
