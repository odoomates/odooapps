/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";

const { Component } = owl;
const { useState } = owl.hooks;

const RIGHTS = () => [
    ["perm_read", _t("Read")],
    ["perm_create", _t("Create")],
    ["perm_write", _t("Edit")],
    ["perm_unlink", _t("Delete")],
];
const FIELD_MODES = () => [
    ["keep", _t("Visible")],
    ["readonly", _t("Read-only")],
    ["hide", _t("Hidden")],
    ["required", _t("Required")],
];
const BUTTON_MODES = () => [
    ["visible", _t("Visible")],
    ["hide", _t("Hidden")],
    ["hide_block", _t("Blocked")],
];
const LEVELS = () => [
    ["full", _t("Full access")],
    ["user", _t("No configuration")],
    ["readonly", _t("Read only")],
    ["none", _t("No access")],
];
// the view elements a menu can hide, one section each (functions: Odoo 16
// loads the translations after the modules)
const ELEMENT_SECTIONS = () => [
    ["pages", "page", _t("Pages"), _t("No page (tab) on the form of this menu.")],
    ["filters", "filter", _t("Filters"), _t("No filter in the search of this menu.")],
    ["views", "view", _t("Views"), _t("This menu opens a single view.")],
];

/**
 * The settings of one menu of a profile: the rights and records of its data,
 * its fields, buttons, tabs and filters, print and action entries and
 * switches; for a menu with children, what it passes down to them; for an app,
 * its allowed records. Every change is written at once by the server.
 */
export class MenuPanel extends Component {
    constructor() {
        super(...arguments);
        this.state = useState({ open: { rights: true }, fieldSearch: "", choices: {} });
        this.RIGHTS = RIGHTS();
        this.FIELD_MODES = FIELD_MODES();
        this.BUTTON_MODES = BUTTON_MODES();
        this.LEVELS = LEVELS();
    }

    willStart() {
        return this.loadChoices();
    }

    /** The changes go to the menu tree, which writes them (Odoo 15 passes no
     * callback to a component: an event). */
    applyChange(change) {
        this.trigger("om-apply", change);
    }

    openRule() {
        this.trigger("om-open-rule");
    }

    resetMenu() {
        return this.applyChange({ kind: "menu_reset" });
    }

    resetData() {
        return this.applyChange({ kind: "data_reset" });
    }

    /** A box of the template: OWL 1 gives the event last. */
    onCheck(method, ...args) {
        const ev = args.pop();
        return this[method](...args, ev.target.checked);
    }

    get panel() {
        return this.props.panel;
    }

    get isData() {
        return Boolean(this.panel.model);
    }

    get isBranch() {
        return this.panel.menu.has_children;
    }

    /** The values shown for "everything below": this menu's own rule, else the
     * one it inherits, else full access. */
    get branchValues() {
        return this.panel.rule || this.panel.inherited || {
            perm_read: true, perm_create: true, perm_write: true, perm_unlink: true,
            records: "all", edit_draft_only: false, include_shared: false,
        };
    }

    get branchSource() {
        if (this.panel.rule) {
            return _t("Set on this menu.");
        }
        if (this.panel.inherited) {
            return sprintf(_t("From %s. Change a box to set it here."), this.panel.inherited.menu);
        }
        return _t("Nothing set: full access. Change a box to restrict everything below.");
    }

    get dataSource() {
        const panel = this.panel;
        if (panel.source === "data") {
            return _t("Set on this data.");
        }
        if (panel.source === "menu") {
            return _t("From the menu above. Change a box to set it on this data.");
        }
        return _t("Full access.");
    }

    get recordChoices() {
        const choices = [...this.panel.record_choices];
        const current = this.panel.rights.records;
        if (current === "custom") {
            choices.push(["custom", _t("Custom filter")]);
        } else if (current === "filter") {
            choices.push(["filter", _t("From the menu above")]);
        }
        return choices;
    }

    get branchRecordChoices() {
        return Object.entries(this.panel.record_labels);
    }

    get shownFields() {
        const search = this.state.fieldSearch.trim().toLowerCase();
        const fields = this.panel.fields || [];
        return search ? fields.filter((field) => field.label.toLowerCase().includes(search)) : fields;
    }

    get reports() {
        return (this.panel.print || []).filter((entry) => entry.type === "ir.actions.report");
    }

    get actions() {
        return (this.panel.print || []).filter((entry) => entry.type !== "ir.actions.report");
    }

    get switchItems() {
        return Object.entries(this.panel.switch_labels);
    }

    onFieldSearch(ev) {
        this.state.fieldSearch = ev.target.value;
    }

    count(list, predicate) {
        return (list || []).filter(predicate).length;
    }

    countLabel(count, label) {
        return count ? sprintf(_t("%(label)s (%(count)s)"), { label, count }) : label;
    }

    get sections() {
        const panel = this.panel;
        const switches = Object.keys(panel.switch_labels).filter((flag) => panel.rights[flag]).length;
        return [
            { key: "fields", label: this.countLabel(
                this.count(panel.fields, (field) => field.mode !== "keep"), _t("Fields")) },
            { key: "buttons", label: this.countLabel(
                this.count(panel.buttons, (button) => button.mode !== "visible"), _t("Buttons")) },
            ...ELEMENT_SECTIONS().map(([key, type, label, empty]) => ({
                key, elementType: type, empty,
                label: this.countLabel(
                    this.count(this.elementsOf(type), (element) => element.hidden), label),
            })),
            { key: "print", entries: this.reports, empty: _t("No report for this data."),
              label: this.countLabel(this.count(this.reports, (entry) => entry.hidden), _t("Print")) },
            { key: "actions", entries: this.actions, empty: _t("Nothing in the Action menu of this data."),
              label: this.countLabel(this.count(this.actions, (entry) => entry.hidden), _t("Action Menu")) },
            { key: "switches", label: this.countLabel(switches, _t("Switches")) },
        ];
    }

    elementsOf(type) {
        return (this.panel.elements || []).filter((element) => element.element_type === type);
    }

    toggleSection(key) {
        this.state.open[key] = !this.state.open[key];
    }

    async loadChoices() {
        for (const kind of this.panel.allowed || []) {
            if (!this.state.choices[kind.model]) {
                this.state.choices[kind.model] = await this.env.services.rpc({
                    model: kind.model, method: "search_read", args: [[], ["display_name"]], kwargs: { limit: 500 },
                });
            }
        }
    }

    // changes

    setDataRight(name, value) {
        return this.applyChange({ kind: "data_rights", [name]: value });
    }

    setBranchRight(name, value) {
        return this.applyChange({ kind: "menu_rights", [name]: value });
    }

    onDataRecords(ev) {
        if (["custom", "filter"].includes(ev.target.value)) {
            return;
        }
        return this.applyChange({ kind: "data_rights", records: ev.target.value });
    }

    onBranchRecords(ev) {
        return this.applyChange({ kind: "menu_rights", records: ev.target.value });
    }

    setFieldMode(field, mode) {
        return this.setField(field, mode);
    }

    setField(field, mode, condition = field.condition) {
        return this.applyChange({ kind: "field", field: field.name, mode, condition });
    }

    noExportTitle(field) {
        return field.no_export
            ? _t("Kept out of the exports: click to allow exporting it")
            : _t("Exported: click to keep it out of the exports");
    }

    setNoExport(field, value) {
        return this.applyChange({
            kind: "field", field: field.name, mode: field.mode, condition: field.condition, no_export: value,
        });
    }

    onFieldCondition(field, ev) {
        if (ev.target.value !== field.condition) {
            return this.setField(field, field.mode, ev.target.value);
        }
    }

    buttonMode(button) {
        return button.mode === "block" ? "hide_block" : button.mode;
    }

    setButton(button, mode) {
        return this.applyChange({
            kind: "button",
            button_type: button.button_type,
            button_name: button.button_name,
            label: button.label,
            mode,
            condition: button.condition,
        });
    }

    setElement(element, shown) {
        return this.applyChange({
            kind: "element",
            element_type: element.element_type,
            element_name: element.element_name,
            label: element.label,
            hidden: !shown,
        });
    }

    setPrint(entry, shown) {
        return this.applyChange({ kind: "print", type: entry.type, id: entry.id, hidden: !shown });
    }

    setGrant(grant, ev) {
        return this.applyChange({
            kind: "grant", privilege_id: grant.privilege_id, group_id: parseInt(ev.target.value) || false,
        });
    }

    setLevel(level) {
        return this.applyChange({ kind: "level", level });
    }

    showMenu() {
        return this.applyChange({ kind: "hide_menu", hidden: false });
    }

    onAddAllowed(kind, ev) {
        const id = parseInt(ev.target.value);
        ev.target.value = "";
        if (id) {
            return this.applyChange({ kind: "allowed", allowed_kind: kind.kind, add: id });
        }
    }

    removeAllowed(kind, record) {
        return this.applyChange({ kind: "allowed", allowed_kind: kind.kind, remove: record.line_id });
    }

    setPerUser(kind, value) {
        return this.applyChange({ kind: "allowed", allowed_kind: kind.kind, per_user: value });
    }

    allowedChoices(kind) {
        const taken = new Set(kind.records.map((record) => record.id));
        return (this.state.choices[kind.model] || []).filter((record) => !taken.has(record.id));
    }
}

MenuPanel.template = "om_access_manager.MenuPanel";
