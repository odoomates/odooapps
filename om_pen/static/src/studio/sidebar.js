import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { evaluateExpr } from "@web/core/py_js/py";
import { ExpressionEditorDialog } from "@web/core/expression_editor_dialog/expression_editor_dialog";
import { DomainSelectorDialog } from "@web/core/domain_selector_dialog/domain_selector_dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { VIEW_SETTINGS } from "./view_settings";
import { FieldDeleteDialog, FieldSettingsDialog } from "./dialogs";

export const NEW_FIELD_KINDS = [
    { kind: "char", label: _t("Text"), icon: "text_fields" },
    { kind: "text", label: _t("Multiline Text"), icon: "subtitles" },
    { kind: "html", label: _t("Rich Text"), icon: "format_bold" },
    { kind: "integer", label: _t("Integer"), icon: "tag" },
    { kind: "float", label: _t("Decimal"), icon: "calculate" },
    { kind: "monetary", label: _t("Amount"), icon: "payments" },
    { kind: "boolean", label: _t("Checkbox"), icon: "check_box" },
    { kind: "date", label: _t("Date"), icon: "calendar_today" },
    { kind: "datetime", label: _t("Date & Time"), icon: "schedule" },
    { kind: "selection", label: _t("Selection"), icon: "list_alt" },
    { kind: "priority", label: _t("Priority"), icon: "star" },
    { kind: "many2one", label: _t("Link"), icon: "link" },
    { kind: "many2many", label: _t("Tags"), icon: "sell" },
    { kind: "one2many", label: _t("Lines"), icon: "table_rows" },
    { kind: "binary", label: _t("File"), icon: "attach_file" },
    { kind: "image", label: _t("Image"), icon: "image" },
    { kind: "signature", label: _t("Signature"), icon: "edit_square" },
    { kind: "related", label: _t("Related Field"), icon: "account_tree" },
    { kind: "total", label: _t("Count Or Total"), icon: "pie_chart" },
];

export const FORM_COMPONENTS = [
    { kind: "notebook", label: _t("Tabs"), icon: "folder", tag: "notebook" },
    { kind: "page", label: _t("Tab"), icon: "label", tag: "page" },
    { kind: "columns", label: _t("Columns"), icon: "view_column", tag: "group" },
    { kind: "group", label: _t("Group"), icon: "crop_square", tag: "group" },
    { kind: "separator", label: _t("Section Title"), icon: "title", tag: "separator" },
];

export const SPECIAL_ACTIONS = [
    { key: "ribbon", label: _t("Ribbon"), icon: "bookmark" },
    { key: "smart_button", label: _t("Smart Button"), icon: "widgets" },
    { key: "header_button", label: _t("Header Button"), icon: "toggle_on" },
    { key: "stages", label: _t("Stages"), icon: "flag" },
    { key: "chatter", label: _t("Chatter"), icon: "forum" },
];

const MODIFIERS = [
    { attr: "invisible", label: _t("Invisible") },
    { attr: "required", label: _t("Required"), tags: ["field"] },
    { attr: "readonly", label: _t("Read-only"), tags: ["field"] },
];

const RELATIONAL_OPTIONS = [
    { key: "no_create", label: _t("Cannot create") },
    { key: "no_quick_create", label: _t("No quick create") },
    { key: "no_create_edit", label: _t("No create and edit") },
    { key: "no_open", label: _t("Cannot open") },
];

const RIBBON_COLORS = [
    ["text-bg-danger", _t("Red")],
    ["text-bg-success", _t("Green")],
    ["text-bg-warning", _t("Yellow")],
    ["text-bg-info", _t("Blue")],
    ["text-bg-primary", _t("Purple")],
    ["text-bg-secondary", _t("Grey")],
];

function modifierMode(value) {
    if (!value || ["0", "False", "false"].includes(value.trim())) {
        return "off";
    }
    if (["1", "True", "true"].includes(value.trim())) {
        return "always";
    }
    return "condition";
}

export class StudioSidebar extends Component {
    static template = "om_pen.StudioSidebar";
    props = useProps();

    setup() {
        this.store = this.props.store;
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.ui = proxy({ search: "", groups: [], fieldInfo: null, loadingInfo: null });
        this.NEW_FIELD_KINDS = NEW_FIELD_KINDS;
        this.FORM_COMPONENTS = FORM_COMPONENTS;
        this.SPECIAL_ACTIONS = SPECIAL_ACTIONS;
        this.RELATIONAL_OPTIONS = RELATIONAL_OPTIONS;
        this.RIBBON_COLORS = RIBBON_COLORS;
        onWillStart(async () => {
            this.ui.groups = await this.orm.call("om.pen.studio", "studio_groups", []);
        });
    }

    get viewType() {
        return this.store.view?.view_type;
    }

    get node() {
        return this.store.selectedNode;
    }

    // ------------------------------------------------------------------
    // Add tab
    // ------------------------------------------------------------------

    get canDrop() {
        return ["form", "list", "kanban"].includes(this.viewType);
    }

    get existingFields() {
        const model = this.store.focusModel;
        const fields = model === this.store.info.model
            ? this.store.view.all_fields
            : this.store.view.related_models[model]?.fields || {};
        const inView = new Set(
            Object.values(this.store.nodes)
                .filter((n) => n.tag === "field" && n.model === model)
                .map((n) => n.attrs.name)
        );
        const search = this.ui.search.trim().toLowerCase();
        return Object.values(fields)
            .map((f) => ({ name: f.name, string: f.string || f.name, type: f.type, inView: inView.has(f.name) }))
            .filter((f) => !search || f.string.toLowerCase().includes(search) || f.name.includes(search))
            .sort((a, b) => a.inView - b.inView || a.string.localeCompare(b.string));
    }

    get focusLabel() {
        const model = this.store.focusModel;
        if (model === this.store.info.model) {
            return "";
        }
        return model;
    }

    startDrag(ev, drag) {
        if (ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        this.store.state.drag = { model: this.store.focusModel, ...drag };
        this.store.state.dragPos = { x: ev.clientX, y: ev.clientY };
    }

    // ------------------------------------------------------------------
    // Properties tab
    // ------------------------------------------------------------------

    get nodeFields() {
        const node = this.node;
        if (!node) {
            return {};
        }
        return this.store.view.related_models[node.model]?.fields || this.store.view.fields;
    }

    get nodeLabel() {
        return this.store.labelOf(this.node);
    }

    attr(name) {
        return this.node?.attrs[name] || "";
    }

    async setAttr(name, value) {
        if ((this.node.attrs[name] || "") === (value || "")) {
            return;
        }
        await this.store.setAttrs(this.node.id, { [name]: value || null });
    }

    onTextChange(name, ev) {
        return this.setAttr(name, ev.target.value.trim());
    }

    modifiers() {
        const node = this.node;
        const list = MODIFIERS.filter((m) => !m.tags || m.tags.includes(node.tag));
        if (node.tag === "field" && (this.viewType === "list" || this.store.view.nodes[node.parent]?.tag === "list")) {
            list.push({ attr: "column_invisible", label: _t("Hidden column") });
        }
        return list.map((m) => ({ ...m, value: this.attr(m.attr), mode: modifierMode(this.attr(m.attr)) }));
    }

    async setModifier(modifier, mode) {
        if (mode === "off") {
            return this.setAttr(modifier.attr, "");
        }
        if (mode === "always") {
            return this.setAttr(modifier.attr, "True");
        }
        this.editCondition(modifier);
    }

    editCondition(modifier) {
        const current = modifier.mode === "condition" ? modifier.value : "False";
        this.dialog.add(ExpressionEditorDialog, {
            resModel: this.node.model,
            fields: this.nodeFields,
            expression: current,
            onConfirm: (expression) => this.setAttr(modifier.attr, expression),
        });
    }

    get widgets() {
        const node = this.node;
        if (!node?.field_type) {
            return [];
        }
        const entries = registry.category("fields").getEntries();
        const result = [];
        for (const [key, value] of entries) {
            if (key.includes(".")) {
                continue;
            }
            const types = value.supportedTypes || [];
            if (types.includes(node.field_type) && value.displayName) {
                result.push({ key, label: value.displayName });
            }
        }
        return result.sort((a, b) => a.label.localeCompare(b.label));
    }

    get selectedGroups() {
        const value = this.attr("groups");
        return value ? value.split(",").map((x) => x.trim()) : [];
    }

    groupName(xmlid) {
        return this.ui.groups.find((g) => g.xmlid === xmlid)?.name || xmlid;
    }

    get availableGroups() {
        const chosen = new Set(this.selectedGroups);
        return this.ui.groups.filter((g) => !chosen.has(g.xmlid));
    }

    addGroup(ev) {
        const xmlid = ev.target.value;
        ev.target.value = "";
        if (xmlid) {
            this.setAttr("groups", [...this.selectedGroups, xmlid].join(","));
        }
    }

    removeGroup(xmlid) {
        this.setAttr("groups", this.selectedGroups.filter((x) => x !== xmlid).join(","));
    }

    get options() {
        try {
            return evaluateExpr(this.attr("options") || "{}") || {};
        } catch {
            return {};
        }
    }

    setOption(key, value) {
        const options = { ...this.options };
        if (value) {
            options[key] = true;
        } else {
            delete options[key];
        }
        const text = Object.keys(options).length
            ? `{${Object.entries(options).map(([k, v]) => `'${k}': ${JSON.stringify(v).replace(/^true$/, "True").replace(/^false$/, "False")}`).join(", ")}}`
            : "";
        return this.setAttr("options", text);
    }

    editDomain() {
        const node = this.node;
        this.dialog.add(DomainSelectorDialog, {
            resModel: node.relation,
            domain: this.attr("domain") || "[]",
            isDebugMode: true,
            title: _t("Records offered in %s", this.nodeLabel),
            onConfirm: (domain) => this.setAttr("domain", domain === "[]" ? "" : domain),
        });
    }

    get isNumeric() {
        return ["integer", "float", "monetary"].includes(this.node?.field_type);
    }

    get isRelational() {
        return ["many2one", "many2many"].includes(this.node?.field_type);
    }

    get inList() {
        const node = this.node;
        return node?.tag === "field" && (this.viewType === "list" || this.store.view.nodes[node.parent]?.tag === "list");
    }

    openFieldSettings() {
        const node = this.node;
        this.dialog.add(FieldSettingsDialog, {
            model: node.model,
            fieldName: node.attrs.name,
            onSaved: () => this.store.reload(),
        });
    }

    deleteField() {
        const node = this.node;
        this.dialog.add(FieldDeleteDialog, {
            model: node.model,
            fieldName: node.attrs.name,
            onDeleted: async () => {
                this.store.state.selected = null;
                await this.store.reload();
                this.store.state.canvasKey++;
            },
        });
    }

    removeNode() {
        const label = this.nodeLabel;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove from the view"),
            body: _t("Remove %s from this view? Nothing changes for others until you publish.", label),
            confirmLabel: _t("Remove"),
            confirm: () => this.store.remove(this.node.id),
            cancel: () => {},
        });
    }

    // ------------------------------------------------------------------
    // View tab
    // ------------------------------------------------------------------

    get rootNode() {
        return this.store.node(this.store.rootId);
    }

    get viewSettings() {
        return VIEW_SETTINGS[this.viewType] || [];
    }

    rootAttr(name) {
        return this.rootNode?.attrs[name] || "";
    }

    isOn(setting) {
        const value = this.rootAttr(setting.attr);
        if (!value) {
            return setting.default ?? false;
        }
        return !["0", "false", "False"].includes(value);
    }

    setRoot(setting, value) {
        let text = value;
        if (setting.type === "bool") {
            text = value === (setting.default ?? false) ? "" : value ? "1" : "0";
        }
        return this.store.setAttrs(this.store.rootId, { [setting.attr]: text || null });
    }

    settingFields(setting) {
        const fields = this.store.view.all_fields;
        return Object.values(fields)
            .filter((f) => !setting.fieldTypes || setting.fieldTypes.includes(f.type))
            .filter((f) => f.store || setting.anyField)
            .sort((a, b) => a.string.localeCompare(b.string));
    }

    get chartFields() {
        return Object.values(this.store.nodes).filter(
            (n) => n.tag === "field" && n.parent === this.store.rootId
        );
    }

    addChartField(ev, type) {
        const name = ev.target.value;
        ev.target.value = "";
        if (!name) {
            return;
        }
        return this.store.insert(this.store.rootId, "inside", {
            kind: "field",
            name,
            attrs: type ? { type } : {},
        });
    }

    get numericFields() {
        return Object.values(this.store.view.all_fields)
            .filter((f) => ["integer", "float", "monetary"].includes(f.type) && f.store)
            .sort((a, b) => a.string.localeCompare(b.string));
    }

    get groupableFields() {
        return Object.values(this.store.view.all_fields)
            .filter((f) => f.store && !["one2many", "binary", "html", "text"].includes(f.type))
            .sort((a, b) => a.string.localeCompare(b.string));
    }

    confirmReset() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Back to the original view"),
            body: _t(
                "Every change made to this view is undone in the draft. The view stays as it is for others until you publish."
            ),
            confirmLabel: _t("Undo all changes"),
            confirm: () => this.store.reset(),
            cancel: () => {},
        });
    }
}
