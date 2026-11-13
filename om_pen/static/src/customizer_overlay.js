import {
    Component,
    proxy,
    useListener,
    useOnChange,
    onWillStart,
    onMounted,
    onWillUnmount,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { customizerState, archOptions, bind, fieldsInView } from "./customizer_state";
import { AddFieldDialog, TYPE_ICONS } from "./add_field_dialog";
import { DropPreview } from "./drop_preview";
import { buildExpression } from "./condition_builder";
import { ModifierControl } from "./modifier_control";

const RELATIONAL_TYPES = ["many2one", "many2many"];

// What stands for a field on screen: a field widget, and in a list also the column
// header and the cells - most list columns are plain text, not widgets.
const FIELD_NODE =
    ".o_field_widget[name], .o_list_renderer th[data-name], .o_list_renderer td.o_data_cell[name]";

/** The node of the field under `element`, or null. */
function fieldNodeFrom(element) {
    const node = element?.closest?.(FIELD_NODE);
    if (node && !node.classList.contains("o_field_widget") && node.closest(".o_field_x2many")) {
        // a cell of a list embedded in a form is a field of another model: the field
        // that matters here is the x2many itself
        return node.closest(".o_field_widget[name]");
    }
    return node;
}

function fieldNameOf(node) {
    return node.getAttribute("name") || node.dataset.name;
}

/** List columns sit side by side: left and right decide before and after. */
function isColumn(node) {
    return node.matches("th, td");
}

/** '' keeps the standard behaviour, '1'/'0' force it, anything else is an expression. */
function toMode(value) {
    if (!value) {
        return "";
    }
    return ["0", "1"].includes(value) ? value : "expr";
}

function fromMode(entry) {
    return entry.mode === "expr" ? entry.expr.trim() : entry.mode;
}

export class CustomizerOverlay extends Component {
    static template = "om_pen.CustomizerOverlay";
    static components = { ModifierControl };
    bind = bind;

    setup() {
        this.customizer = useService("om_pen");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.state = proxy(customizerState);
        this.draft = proxy(this.emptyDraft());
        this.actionsDraft = proxy({});
        this.ui = proxy({
            tab: "field",
            groupSearch: "",
            groups: [],
            pageTitle: "",
            changeSearch: "",
            openSections: { appearance: true, behaviour: true, visibility: false, relational: true },
            // the draft as it was loaded, to tell whether anything was changed since;
            // reactive, so a fresh load alone settles `dirty`
            pristine: "",
        });
        // the Add tab: field types to drag in as new fields, and the fields of the
        // model that are not on the view yet
        this.palette = proxy({ types: [], search: "", models: null });
        this.preview = new DropPreview();

        onWillStart(async () => {
            this.palette.types = await this.orm.call("om.pen.view", "field_types", []);
            // display_name is computed on res.groups, so it cannot be ordered
            // on in SQL; name can, and display_name is still fine to read
            this.ui.groups = await this.orm.searchRead(
                "res.groups", [], ["display_name"], { order: "name", limit: 400 }
            );
        });

        useListener(document, "click", this.onDocumentClick.bind(this), { capture: true });
        useListener(document, "keydown", this.onKeydown.bind(this));
        // pointer events rather than HTML5 drag and drop: the form is rendered outside
        // this component, and pointer events are what Odoo's own sortable uses
        useListener(document, "pointerdown", this.onPointerDown.bind(this), { capture: true });
        useListener(document, "pointermove", this.onPointerMove.bind(this), { capture: true });
        useListener(document, "pointerup", this.onPointerUp.bind(this), { capture: true });
        this.drag = null;
        this.swallowNextClick = false;

        // the marks live on the form's own nodes, and any re-render - switching record,
        // paging, the soft_reload after a publish - throws them away, so they are put
        // back whenever the content changes
        this.observer = new MutationObserver(() => this.scheduleMark());
        onMounted(() => this.observeContent());
        onWillUnmount(() => {
            this.observer.disconnect();
            this.preview.clear();
        });

        // these react to state the panel itself writes; they run as effects of their
        // own, apart from rendering, so a write in one never lands mid-render
        // the stored rule counts too: customize mode opens before its rules arrive, and
        // a field picked in that window must still get its rule once they do. Compared
        // by content, so a reload that returns the same rule keeps half-typed edits.
        useOnChange(
            () => [
                this.state.selected,
                this.state.active,
                JSON.stringify(this.state.rules[this.state.selected] || null),
            ],
            () => {
                this.loadDraft();
                // a field was just picked - placed from the Add tab, or back from a
                // reload: show it, wherever the panel was
                if (this.state.selected && this.ui.tab === "add") {
                    this.ui.tab = "field";
                }
            }
        );
        // a braced body matters here: an effect's return value is its cleanup
        // function, and Object.assign returns the target object
        useOnChange(
            () => [this.state.actions],
            () => {
                Object.assign(this.actionsDraft, this.state.actions);
            }
        );
        // the service needs to know about unsaved edits to guard leaving
        useOnChange(
            () => [this.dirty],
            (dirty) => {
                this.state.dirty = dirty;
            }
        );
        useOnChange(
            () => [this.state.selected, this.state.active, this.state.rules],
            () => {
                this.markFields();
            }
        );
    }

    // ------------------------------------------------------------------
    // draft
    // ------------------------------------------------------------------

    emptyCondition() {
        return { join: "and", rows: [], raw: false };
    }

    emptyDraft() {
        return {
            label: "",
            help_text: "",
            widget: "",
            placeholder: "",
            optional: "",
            invisible: { mode: "", expr: "", cond: this.emptyCondition() },
            readonly: { mode: "", expr: "", cond: this.emptyCondition() },
            required: { mode: "", expr: "", cond: this.emptyCondition() },
            column_invisible: { mode: "", expr: "", cond: this.emptyCondition() },
            opt_no_open: false,
            opt_no_create: false,
            opt_no_quick_create: false,
            opt_no_create_edit: false,
            group_ids: [],
        };
    }

    loadDraft() {
        Object.assign(this.draft, this.emptyDraft());
        // the label box starts on the label the field actually shows, so it can be
        // edited rather than retyped from scratch
        this.draft.label = this.currentLabel;
        const rule = this.state.rules[this.state.selected];
        if (!rule) {
            this.ui.pristine = JSON.stringify(this.draft);
            return;
        }
        // the label box already holds the rule's label, or the one shown when the
        // rule renames nothing
        this.draft.help_text = rule.help_text || "";
        this.draft.widget = rule.widget || "";
        this.draft.placeholder = rule.placeholder || "";
        this.draft.optional = rule.optional || "";
        const conditions = rule.condition_data || {};
        for (const name of ["invisible", "readonly", "required", "column_invisible"]) {
            this.draft[name].mode = toMode(rule[name]);
            this.draft[name].expr = toMode(rule[name]) === "expr" ? rule[name] : "";
            // a condition built in the panel comes back as rows; one typed by hand, or
            // written before this existed, has nothing stored and stays raw
            const stored = conditions[name];
            this.draft[name].cond = stored
                ? { join: stored.join || "and", rows: [...(stored.rows || [])], raw: false }
                : { ...this.emptyCondition(), raw: Boolean(this.draft[name].expr) };
        }
        for (const name of ["opt_no_open", "opt_no_create", "opt_no_quick_create", "opt_no_create_edit"]) {
            this.draft[name] = Boolean(rule[name]);
        }
        this.draft.group_ids = [...(rule.group_ids || [])];
        this.ui.pristine = JSON.stringify(this.draft);
    }

    /**
     * The caption a clicked field shows on screen. A field can sit on a view more than
     * once under different captions, and this is what tells which one was meant.
     */
    shownCaption(node) {
        if (isColumn(node)) {
            const header = node.matches("th")
                ? node
                : node.closest("table")?.querySelector(`th[data-name="${CSS.escape(fieldNameOf(node))}"]`);
            return header?.textContent.trim() || "";
        }
        const id = node.querySelector("[id]")?.id;
        const label = id && document.querySelector(`label.o_form_label[for="${CSS.escape(id)}"]`);
        if (!label) {
            return "";
        }
        // without the "?" a label carries when it has a tooltip
        const text = label.cloneNode(true);
        text.querySelectorAll("sup").forEach((sup) => sup.remove());
        return text.textContent.trim();
    }

    /** The label the field shows today: the customized one, else the view's, else the model's. */
    get currentLabel() {
        const name = this.state.selected;
        if (!name) {
            return "";
        }
        const rule = this.state.rules[name];
        if (rule?.label) {
            return rule.label;
        }
        return this.state.shownLabel || this.inheritedLabel;
    }

    /** The label the field would show with no rule at all. */
    get inheritedLabel() {
        const name = this.state.selected;
        const node = this.state.config?.viewArch?.querySelector(
            `field[name="${CSS.escape(name)}"]`
        );
        return node?.getAttribute("string") || this.state.fields[name]?.string || name;
    }

    /**
     * What the label box resets to: the caption that was clicked, which for a field
     * shown under several captions is not necessarily the view's first one. Once a
     * rule renamed it, the screen shows the new label, so only the view's is known.
     */
    get baseLabel() {
        const renamed = this.state.rules[this.state.selected]?.label;
        return (!renamed && this.state.shownLabel) || this.inheritedLabel;
    }

    get dirty() {
        return this.ui.pristine !== JSON.stringify(this.draft);
    }

    /** Widgets the web client can actually render for this field's type. */
    get widgetChoices() {
        const type = this.selectedField.type;
        if (!type) {
            return [];
        }
        const choices = [];
        for (const [name, descriptor] of registry.category("fields").getEntries()) {
            if (name.includes(".")) {
                continue; // view-specific variants such as list.many2one
            }
            if ((descriptor.supportedTypes || []).includes(type)) {
                choices.push({ name, label: descriptor.displayName || name });
            }
        }
        return choices.sort((a, b) => a.label.localeCompare(b.label));
    }

    observeContent() {
        const content = document.querySelector(".o_action_manager") || document.body;
        this.observer.observe(content, { childList: true, subtree: true });
    }

    scheduleMark() {
        if (this.markScheduled) {
            return;
        }
        this.markScheduled = true;
        requestAnimationFrame(() => {
            this.markScheduled = false;
            this.markFields();
        });
    }

    /** Outline the selected field, and mark every field that already carries a rule. */
    markFields() {
        // our own class changes would otherwise wake the observer again, forever
        this.observer.disconnect();
        try {
            this.applyMarks();
        } finally {
            if (this.state.active) {
                this.observeContent();
            }
        }
    }

    applyMarks() {
        for (const node of document.querySelectorAll(
            ".o_om_pen_selected, .o_om_pen_touched"
        )) {
            node.classList.remove("o_om_pen_selected", "o_om_pen_touched");
        }
        if (!this.state.active) {
            return;
        }
        const nodeOf = (name) =>
            document.querySelector(
                `.o_field_widget[name="${CSS.escape(name)}"], .o_list_renderer:not(.o_field_x2many .o_list_renderer) th[data-name="${CSS.escape(name)}"]`
            );
        for (const name of Object.keys(this.state.rules)) {
            nodeOf(name)?.classList.add("o_om_pen_touched");
        }
        if (this.state.selected) {
            nodeOf(this.state.selected)?.classList.add("o_om_pen_selected");
        }
    }

    // ------------------------------------------------------------------
    // events
    // ------------------------------------------------------------------

    onDocumentClick(ev) {
        if (!this.state.active) {
            return;
        }
        if (this.swallowNextClick) {
            // a drag finishes with a click; it must not also select the field
            this.swallowNextClick = false;
            ev.preventDefault();
            ev.stopPropagation();
            return;
        }
        if (ev.target.closest(".o_om_pen_ui, .modal")) {
            return; // our own chrome
        }
        if (this.preview.editing) {
            return; // a new field is being named in place
        }
        const page = ev.target.closest(".o_notebook .nav-link");
        if (page && this.state.adding) {
            return; // let the user switch tabs while looking for a drop target
        }
        const node = fieldNodeFrom(ev.target);
        if (!node) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        if (this.state.adding) {
            this.customizer.placeField(fieldNameOf(node));
            return;
        }
        this.customizer.select(fieldNameOf(node), this.shownCaption(node));
        this.ui.tab = "field";
    }

    // ------------------------------------------------------------------
    // dragging
    // ------------------------------------------------------------------

    onPointerDown(ev) {
        // `> 0` rather than `!== 0`: a synthetic pointer event may carry no button at
        // all, and only a secondary button should be ignored
        if (!this.state.active || ev.button > 0 || this.preview.editing) {
            return;
        }
        // a tile or a field of the Add tab, dragged in from the panel
        const source = ev.target.closest(".o_om_pen_source");
        if (source) {
            ev.preventDefault(); // no text selection while dragging
            const { ttype, field } = source.dataset;
            const info = field ? this.state.fields[field] : null;
            this.drag = {
                source: "palette",
                ttype: ttype || null,
                field: field || null,
                label: field ? info?.string || field : this.typeLabel(ttype),
                icon: TYPE_ICONS[ttype || info?.type] || "add",
                x: ev.clientX,
                y: ev.clientY,
            };
            return;
        }
        const chip = ev.target.closest(".o_om_pen_chip");
        if (chip && this.state.adding) {
            this.drag = { field: this.state.adding, isNew: true, x: ev.clientX, y: ev.clientY };
            this.describeDrag(this.drag);
            return;
        }
        if (ev.target.closest(".o_om_pen_ui, .modal")) {
            return;
        }
        const node = fieldNodeFrom(ev.target);
        if (!node) {
            return;
        }
        this.drag = {
            field: fieldNameOf(node),
            isNew: false,
            x: ev.clientX,
            y: ev.clientY,
        };
        this.describeDrag(this.drag);
    }

    /** The caption and icon a dragged field shows in its preview. */
    describeDrag(drag) {
        const info = this.state.fields[drag.field] || {};
        drag.label = info.string || drag.field;
        drag.icon = TYPE_ICONS[info.type] || "open_with";
    }

    typeLabel(ttype) {
        return (this.palette.types.find(([key]) => key === ttype) || [ttype, ttype])[1];
    }

    onPointerMove(ev) {
        if (!this.drag) {
            return;
        }
        if (!this.drag.started) {
            if (Math.hypot(ev.clientX - this.drag.x, ev.clientY - this.drag.y) < 6) {
                return; // a click, not a drag
            }
            this.drag.started = true;
            document.body.classList.add("o_om_pen_dragging");
            this.drag.avatar = this.makeAvatar(this.drag);
        }
        ev.preventDefault();
        this.drag.avatar.style.transform = `translate(${ev.clientX + 14}px, ${ev.clientY + 10}px)`;
        // over the preview itself, keep the target: the slot moving the form around
        // would otherwise flip the target back and forth under a still pointer
        if (this.preview.contains(document.elementFromPoint(ev.clientX, ev.clientY))) {
            return;
        }
        const exclude = this.drag.source === "palette" ? null : this.drag.field;
        this.drag.target = this.dropTargetAt(ev.clientX, ev.clientY, exclude);
        this.preview.show(this.drag.target, this.drag);
    }

    /** The chip that follows the pointer while dragging. */
    makeAvatar(drag) {
        const avatar = document.createElement("div");
        avatar.className = "o_om_pen_ui o_om_pen_avatar";
        const icon = document.createElement("i");
        icon.className = "oi oi-fw me-1";
        icon.dataset.icon = drag.icon;
        avatar.append(icon, document.createTextNode(drag.label || ""));
        document.body.append(avatar);
        return avatar;
    }

    async onPointerUp() {
        const drag = this.drag;
        this.drag = null;
        document.body.classList.remove("o_om_pen_dragging");
        drag?.avatar?.remove();
        if (!drag || !drag.started) {
            return;
        }
        this.swallowNextClick = true;
        const target = drag.target;
        if (!target) {
            this.preview.clear();
            return;
        }
        if (drag.source === "palette" && drag.ttype) {
            await this.dropNewField(drag, target);
            return;
        }
        // the view is reloaded below: the preview must be gone before the renderer
        // patches the form again
        this.preview.clear();
        const pageName = target.kind === "page" ? target.pageName : null;
        if (drag.source === "palette" || drag.isNew) {
            if (drag.source === "palette") {
                this.state.adding = drag.field;
            }
            await this.customizer.placeField(pageName ? null : target.name, {
                pageName,
                position: target.position,
            });
            this.ui.tab = "field";
            return;
        }
        if (pageName) {
            await this.customizer.moveField(drag.field, false, "after", pageName);
        } else {
            await this.customizer.moveField(drag.field, target.name, target.position);
        }
    }

    /**
     * A field type was dropped: name the new field right where it landed, then create
     * it and put it there.
     */
    async dropNewField(drag, target) {
        const needsRelation = RELATIONAL_TYPES.includes(drag.ttype);
        if (needsRelation && !this.palette.models) {
            this.palette.models = await this.orm.searchRead("ir.model", [], ["model", "name"], {
                order: "name",
            });
        }
        const values = await this.preview.edit({
            typeLabel: this.typeLabel(drag.ttype),
            needsRelation,
            needsSelection: drag.ttype === "selection",
            models: this.palette.models,
            anchorRect: target.node.getBoundingClientRect(),
        });
        this.preview.clear();
        if (!values) {
            return;
        }
        const fieldName = await this.orm.call("om.pen.view", "create_field", [
            this.state.config.resModel,
            {
                field_description: values.label,
                ttype: drag.ttype,
                relation: values.relation,
                selection: values.selection,
            },
        ]);
        this.state.adding = fieldName;
        const pageName = target.kind === "page" ? target.pageName : null;
        await this.customizer.placeField(pageName ? null : target.name, {
            pageName,
            position: target.position,
            schemaChanged: true,
        });
    }

    /** Fields of the model that are not on the view yet, for the Add tab. */
    get paletteFields() {
        const shown = new Set(fieldsInView());
        const needle = this.palette.search.trim().toLowerCase();
        return Object.entries(this.state.fields)
            .filter(([name, info]) => !shown.has(name) && !["id", "display_name"].includes(name) && info.type !== "one2many")
            .map(([name, info]) => ({
                name,
                string: info.string || name,
                type: info.type,
                icon: TYPE_ICONS[info.type] || "radio_button_unchecked",
            }))
            .filter(
                (field) =>
                    !needle ||
                    field.string.toLowerCase().includes(needle) ||
                    field.name.toLowerCase().includes(needle)
            )
            .sort((a, b) => a.string.localeCompare(b.string))
            .slice(0, 80);
    }

    get paletteTypes() {
        return this.palette.types.map(([key, label]) => ({
            key,
            label,
            icon: TYPE_ICONS[key] || "add",
        }));
    }

    /**
     * The field the drop lands on, and whether it lands before or after it.
     *
     * An exact hit is preferred, but the pointer often sits on a label, on a table cell
     * or in the gap between two rows, so a near miss falls back to the closest field.
     */
    dropTargetAt(x, y, exclude) {
        // a notebook tab drops the field into that page. Only named pages can be
        // targeted: the engine refuses to match on translated attributes such as the
        // page title, so an unnamed page cannot be addressed at all
        const page = this.pageTargetAt(x, y);
        if (page) {
            return page;
        }
        const element = document.elementFromPoint(x, y);
        let node = fieldNodeFrom(element);
        if (node && fieldNameOf(node) === exclude) {
            node = null;
        }
        if (!node) {
            node = this.closestFieldTo(x, y, exclude);
        }
        if (!node) {
            return null;
        }
        const rect = node.getBoundingClientRect();
        const before = isColumn(node)
            ? x < rect.left + rect.width / 2
            : y < rect.top + rect.height / 2;
        return this.uniqueAnchor({
            name: fieldNameOf(node),
            node,
            position: before ? "before" : "after",
        }, exclude);
    }

    /**
     * Anchor on a field the view has only once.
     *
     * The server places a field next to its anchor by name, and a name matches the
     * first occurrence: on sale.order, date_order is there twice (Quotation Date and
     * Order Date), so "after date_order" lands by the one the user was not looking at.
     * The same spot can be described from the other side - after X is before the
     * field that follows X - so when that neighbour is unique, it is used instead.
     */
    uniqueAnchor(target, exclude) {
        const arch = this.state.config?.viewArch;
        const count = (name) =>
            arch ? arch.querySelectorAll(`field[name="${CSS.escape(name)}"]`).length : 1;
        if (count(target.name) <= 1) {
            return target;
        }
        const group = target.node.closest(".o_inner_group, .o_group, .tab-pane, .o_form_sheet");
        if (!group) {
            return target;
        }
        const siblings = [...group.querySelectorAll(".o_field_widget[name]")].filter(
            (node) =>
                node.getAttribute("name") !== exclude &&
                !node.parentElement.closest(".o_field_widget") && // not inside an x2many
                (node.offsetWidth || node.offsetHeight)
        );
        const index = siblings.indexOf(target.node);
        const neighbour = target.position === "after" ? siblings[index + 1] : siblings[index - 1];
        if (!neighbour || count(neighbour.getAttribute("name")) !== 1) {
            return target;
        }
        return {
            name: neighbour.getAttribute("name"),
            node: neighbour,
            position: target.position === "after" ? "before" : "after",
        };
    }

    /**
     * The notebook tab the pointer is on, or near.
     *
     * Geometry rather than `closest`, because the pointer often lands on the list item
     * that wraps the tab, or in the padding around it.
     */
    pageTargetAt(x, y) {
        let best = null;
        let bestDistance = Infinity;
        for (const link of document.querySelectorAll(".o_notebook .nav-link[name]")) {
            if (!link.getAttribute("name")) {
                continue;
            }
            const rect = link.getBoundingClientRect();
            const dx = Math.max(rect.left - x, 0, x - rect.right);
            const dy = Math.max(rect.top - y, 0, y - rect.bottom);
            const distance = Math.hypot(dx, dy);
            if (distance < bestDistance) {
                bestDistance = distance;
                best = link;
            }
        }
        if (!best || bestDistance > 24) {
            return null;
        }
        return { kind: "page", pageName: best.getAttribute("name"), node: best };
    }

    closestFieldTo(x, y, exclude) {
        let best = null;
        let bestDistance = Infinity;
        for (const candidate of document.querySelectorAll(`.o_content :is(${FIELD_NODE})`)) {
            if (fieldNodeFrom(candidate) !== candidate || fieldNameOf(candidate) === exclude) {
                continue;
            }
            const rect = candidate.getBoundingClientRect();
            if (!rect.width && !rect.height) {
                continue;
            }
            const dx = Math.max(rect.left - x, 0, x - rect.right);
            const dy = Math.max(rect.top - y, 0, y - rect.bottom);
            const distance = Math.hypot(dx, dy);
            if (distance < bestDistance) {
                bestDistance = distance;
                best = candidate;
            }
        }
        // far from everything means the user aimed at nothing
        return bestDistance <= 80 ? best : null;
    }

    onKeydown(ev) {
        if (!this.state.active || this.preview.editing) {
            return;
        }
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            if (this.ui.tab === "view") {
                this.applyActions();
            } else if (this.state.selected && this.dirty) {
                this.applyField();
            }
            return;
        }
        if (ev.key !== "Escape") {
            return;
        }
        if (this.state.adding) {
            this.customizer.cancelAdding();
        } else if (this.state.selected) {
            this.customizer.select(null);
        } else {
            this.customizer.toggle();
        }
    }

    openAddDialog() {
        this.dialog.add(AddFieldDialog, {
            onPicked: (fieldName) => this.customizer.startAdding(fieldName),
        });
    }

    /** Add a field straight into the list or form embedded in an x2many. */
    openSubviewDialog(subview, subViewType) {
        this.dialog.add(AddFieldDialog, {
            target: {
                model: subview.comodel,
                subField: subview.name,
                subViewType,
                label: `${subview.string} · ${subViewType}`,
            },
            onPicked: (fieldName) =>
                this.customizer.addSubviewField(subview.name, subViewType, fieldName),
        });
    }

    // ------------------------------------------------------------------
    // derived
    // ------------------------------------------------------------------

    get selectedField() {
        return this.state.fields[this.state.selected] || {};
    }

    get isRelational() {
        return RELATIONAL_TYPES.includes(this.selectedField.type);
    }

    get isList() {
        return this.state.config?.viewType === "list";
    }

    get isAddedField() {
        return this.state.rules[this.state.selected]?.kind === "add";
    }

    get changes() {
        const needle = this.ui.changeSearch.trim().toLowerCase();
        return Object.entries(this.state.rules)
            .filter(([name]) => !needle || name.toLowerCase().includes(needle))
            .map(([name, rule]) => ({
            name,
            label: this.state.fields[name]?.string || name,
            kind: rule.kind,
            draft: Boolean(rule.draft),
            to_remove: Boolean(rule.to_remove),
            summary: this.summarise(rule),
        }));
    }

    toggleSection(name) {
        this.ui.openSections[name] = !this.ui.openSections[name];
    }

    selectChange(key) {
        this.customizer.select(key);
        this.ui.tab = "field";
    }

    summarise(rule) {
        const parts = [];
        if (rule.kind === "add") {
            parts.push(rule.anchor_field ? `added after ${rule.anchor_field}` : "added");
        }
        if (rule.kind === "move") {
            parts.push(`moved ${rule.position || "after"} ${rule.anchor_field}`);
        }
        if (rule.label) {
            parts.push(_t('renamed to "%s"', rule.label));
        }
        for (const name of ["invisible", "readonly", "required"]) {
            if (rule[name]) {
                parts.push(rule[name] === "1" ? name : `${name} if ${rule[name]}`);
            }
        }
        if (rule.widget) {
            parts.push(`widget ${rule.widget}`);
        }
        if ((rule.group_ids || []).length) {
            parts.push(`restricted to ${rule.group_ids.length} group(s)`);
        }
        return parts.join(", ") || "no change";
    }

    get visibleGroups() {
        const needle = this.ui.groupSearch.trim().toLowerCase();
        if (!needle) {
            return this.ui.groups.slice(0, 12);
        }
        return this.ui.groups
            .filter((group) => group.display_name.toLowerCase().includes(needle))
            .slice(0, 12);
    }

    get selectedGroupNames() {
        return this.ui.groups
            .filter((group) => this.draft.group_ids.includes(group.id))
            .map((group) => group.display_name);
    }

    toggleGroup(groupId) {
        const index = this.draft.group_ids.indexOf(groupId);
        if (index === -1) {
            this.draft.group_ids.push(groupId);
        } else {
            this.draft.group_ids.splice(index, 1);
        }
    }

    get hasNotebook() {
        return Boolean(document.querySelector(".o_notebook"));
    }

    // ------------------------------------------------------------------
    // actions
    // ------------------------------------------------------------------

    async applyField() {
        const label = this.draft.label.trim();
        // storing the caption the field already shows would emit a spec that renames nothing
        const values = {
            label: label === this.baseLabel ? "" : label,
            shown_label: this.state.shownLabel,
            help_text: this.draft.help_text.trim(),
            widget: this.draft.widget.trim(),
            placeholder: this.draft.placeholder.trim(),
            optional: this.isList ? this.draft.optional : "",
            invisible: this.expressionOf("invisible"),
            readonly: this.expressionOf("readonly"),
            required: this.expressionOf("required"),
            column_invisible: this.isList ? this.expressionOf("column_invisible") : "",
            condition_data: this.conditionData(),
            base_options: archOptions(this.state.selected),
            group_ids: [...this.draft.group_ids],
        };
        for (const name of ["opt_no_open", "opt_no_create", "opt_no_quick_create", "opt_no_create_edit"]) {
            values[name] = this.isRelational && this.draft[name];
        }
        await this.customizer.saveField(this.state.selected, values);
        // the draft is stored now, so the panel is no longer holding unapplied work.
        // loadDraft also re-reads the rule, which is what the server actually kept.
        this.loadDraft();
    }

    /** The expression a modifier will carry, from the builder or from the raw box. */
    expressionOf(name) {
        const entry = this.draft[name];
        if (entry.mode !== "expr") {
            return entry.mode;
        }
        if (entry.cond.raw) {
            return entry.expr.trim();
        }
        return buildExpression(entry.cond, this.state.fields);
    }

    /** Only conditions that were actually built in the panel are stored. */
    conditionData() {
        const data = {};
        for (const name of ["invisible", "readonly", "required", "column_invisible"]) {
            const entry = this.draft[name];
            if (entry.mode === "expr" && !entry.cond.raw && entry.cond.rows.length) {
                data[name] = { join: entry.cond.join, rows: entry.cond.rows };
            }
        }
        return data;
    }

    /** Fields the condition rows may refer to: the ones this view actually shows. */
    get conditionFieldNames() {
        return fieldsInView().filter((name) => this.state.fields[name]);
    }

    async clearField() {
        await this.customizer.removeField(this.state.selected);
    }

    async removeRule(fieldName) {
        await this.customizer.removeField(fieldName);
    }

    async applyActions() {
        await this.customizer.saveActions({ ...this.actionsDraft });
    }

    async addPage() {
        const title = this.ui.pageTitle.trim();
        if (!title) {
            return;
        }
        this.ui.pageTitle = "";
        await this.customizer.addPage(title);
    }

    async removePage(pageId) {
        await this.customizer.removePage(pageId);
    }

    async placeInPage(pageId) {
        await this.customizer.placeField(null, { pageId });
    }

    get availableToAdd() {
        const shown = new Set(fieldsInView());
        return Object.keys(this.state.fields).filter((name) => !shown.has(name)).length;
    }
}

registry.category("main_components").add("om_pen.overlay", { Component: CustomizerOverlay });
