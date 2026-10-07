/** @odoo-module **/

import AbstractFieldOwl from "web.AbstractFieldOwl";
import FieldWrapper from "web.FieldWrapper";
import fieldRegistry from "web.field_registry_owl";
import { _lt, _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { MenuPanel } from "./menu_panel";

const { useState } = owl.hooks;

const MODEL = "om.access.profile";

/**
 * Odoo 15's form renders its fields again on every reload (after a save, after
 * the panel wrote through the server): what the tree shows is kept here, per
 * record of the form, and the change waiting for a save is applied by the new
 * field.
 */
const KEPT = new Map();

/**
 * The Menus & Apps tab: the real menu tree of the database, where a profile is
 * configured. A ticked menu is shown, an unticked one is hidden with its whole
 * branch; clicking a menu opens its settings beside the tree (MenuPanel).
 *
 * The field stays a plain many2many of the hidden menus, and only the topmost
 * hidden menu of a branch is kept in it: the engine hides the children of a
 * hidden menu on its own. The panel writes its changes through the server.
 *
 * Under a menu that opens data come the reports and Action menu entries of
 * that data, each with its box: they are hidden through the server too.
 */
export class MenuTreeField extends AbstractFieldOwl {
    constructor() {
        super(...arguments);
        const kept = KEPT.get(this.record.id) || {};
        this.state = useState({
            expanded: kept.expanded || {},
            search: kept.search || "",
            onlyRestricted: kept.onlyRestricted || false,
            selected: kept.selected || null,
            panel: null,
            tree: { menu_rules: {}, models: {}, apps: {}, hidden_prints: [] },
            busy: false,
            appAccess: {},
        });
        this.pending = kept.pending || null;
        // the apps the users of the profile can open follow its users, saved or not
        this.membersKey = null;
        this.menus = {};
        this.children = {};
        this.roots = [];
    }

    async willStart() {
        await super.willStart(...arguments);
        const menus = await this.call("om_menu_tree", []);
        for (const menu of menus) {
            this.menus[menu.id] = menu;
            (this.children[menu.parent_id] = this.children[menu.parent_id] || []).push(menu.id);
        }
        this.roots = menus.filter((menu) => !menu.parent_id).map((menu) => menu.id);
        this.prints = await this.call("om_tree_prints", []);
        await this.loadTreeState();
        await this.observeMembers(this.props.record);
        if (this.state.selected && this.record.res_id) {
            this.state.panel = await this.call("om_menu_panel", [[this.record.res_id], this.state.selected]);
        }
    }

    mounted() {
        super.mounted(...arguments);
        // Odoo 15 builds the field again when another field changes, and draws
        // it from the record as it was before the change: draw it again with
        // the record it has now (the grant of a ticked app)
        this.render();
        if (this.pending && this.record.res_id && !this.record.isDirty()) {
            // the change that waited for the profile to be saved
            const pending = this.pending;
            this.pending = null;
            this.keep();
            this.runPending(pending);
        }
    }

    async willUpdateProps(nextProps) {
        await super.willUpdateProps(...arguments);
        await this.observeMembers(nextProps.record);
    }

    willUnmount() {
        this.keep();
        super.willUnmount(...arguments);
    }

    /** What a new field of the same record shows again. */
    keep(pending = this.pending) {
        KEPT.set(this.record.id, {
            expanded: this.state.expanded,
            search: this.state.search,
            onlyRestricted: this.state.onlyRestricted,
            selected: this.state.selected,
            pending,
        });
    }

    get readonly() {
        return false;
    }

    call(method, args, kwargs = {}) {
        return this.env.services.rpc({ model: MODEL, method, args, kwargs });
    }

    async observeMembers(record) {
        const users = record.data.user_ids;
        const ids = users ? users.res_ids : [];
        const key = ids.join(",");
        if (key !== this.membersKey) {
            this.membersKey = key;
            const resIds = record.res_id ? [record.res_id] : [];
            this.state.appAccess = await this.call("om_app_access", [resIds, ids]);
        }
    }

    async loadTreeState() {
        const resId = this.record.res_id;
        this.state.tree = resId
            ? await this.call("om_tree_state", [[resId]])
            : { menu_rules: {}, models: {}, apps: {}, hidden_prints: [] };
    }

    get hiddenIds() {
        return new Set(this.value.res_ids);
    }

    get grantedIds() {
        const granted = this.record.data.granted_group_ids;
        return new Set(granted ? granted.res_ids : []);
    }

    /** An app that some user of the profile cannot open, and that the
     * profile does not give: shown unticked, ticking it gives it. */
    notGiven(menuId) {
        const info = this.state.appAccess[menuId];
        if (!info || info.open) {
            return false;
        }
        const granted = this.grantedIds;
        return !info.gate_ids.some((id) => granted.has(id));
    }

    descendants(menuId) {
        const result = [];
        const stack = [...(this.children[menuId] || [])];
        while (stack.length) {
            const id = stack.pop();
            result.push(id);
            stack.push(...(this.children[id] || []));
        }
        return result;
    }

    /** What is restricted on a menu itself: its rule, and on its data. */
    marks(menuId) {
        const marks = [];
        const menu = this.menus[menuId];
        const rule = this.state.tree.menu_rules[menuId];
        if (rule) {
            const rights = ["perm_read", "perm_create", "perm_write", "perm_unlink"].filter((name) => !rule[name]);
            marks.push({ icon: "sitemap", title: rights.length || rule.records !== "all"
                ? _t("Restricts everything below") : _t("Set for everything below") });
        }
        if ((this.state.tree.granted_apps || []).includes(menuId)) {
            marks.push({ icon: "key", title: _t("Opens the app to its users") });
        }
        if (this.state.tree.apps && this.state.tree.apps[menuId]) {
            marks.push({ icon: "list-ul", title: _t("Only some records allowed in this app") });
        }
        const data = menu.model && this.state.tree.models[menu.model];
        if (data) {
            if (data.rights.some((right) => !right)) {
                marks.push({ icon: "lock", title: data.rights[0]
                    ? _t("Some rights removed") : _t("No access to the data") });
            }
            if (data.records !== "all") {
                marks.push({ icon: "filter", title: _t("Only some records") });
            }
            if (data.fields || data.elements) {
                marks.push({ icon: "eye-slash", title: _t("Fields, tabs or filters hidden") });
            }
            if (data.buttons) {
                marks.push({ icon: "hand-pointer-o", title: _t("Buttons hidden or blocked") });
            }
            if (data.print) {
                marks.push({ icon: "print", title: _t("Reports or actions hidden") });
            }
            if (data.switches) {
                marks.push({ icon: "toggle-off", title: _t("Switches on") });
            }
        }
        return marks;
    }

    printsOf(menuId) {
        const model = this.menus[menuId].model;
        return (model && this.prints[model]) || [];
    }

    printKey(entry) {
        return `${entry.type},${entry.id}`;
    }

    /** The report and action rows to show under a menu: all of them when
     * unfolded, else those the search or the "only restricted" filter keeps. */
    shownPrints(menuId, search, filtering) {
        const hidden = new Set(this.state.tree.hidden_prints);
        return this.printsOf(menuId).filter((entry) => {
            if (!filtering) {
                return true;
            }
            const isHidden = hidden.has(this.printKey(entry));
            return (!search || entry.label.toLowerCase().includes(search))
                && (!this.state.onlyRestricted || isHidden);
        });
    }

    restricted(menuId, hidden) {
        return hidden.has(menuId) || this.marks(menuId).length > 0;
    }

    matches(menuId, search, hidden) {
        const menu = this.menus[menuId];
        const own = (!search || menu.name.toLowerCase().includes(search)
            || (menu.model_label || "").toLowerCase().includes(search))
            && (!this.state.onlyRestricted || this.restricted(menuId, hidden));
        return own || this.shownPrints(menuId, search, true).length > 0
            || (this.children[menuId] || []).some((id) => this.matches(id, search, hidden));
    }

    /**
     * The rows on screen, depth first. A search, or the "only restricted"
     * filter, shows every branch holding a match, unfolded.
     */
    get rows() {
        const hidden = this.hiddenIds;
        const search = this.state.search.trim().toLowerCase();
        const filtering = Boolean(search) || this.state.onlyRestricted;
        const rows = [];
        const walk = (menuId, depth, parentHidden) => {
            if (filtering && !this.matches(menuId, search, hidden)) {
                return;
            }
            const menu = this.menus[menuId];
            const descendants = this.descendants(menuId);
            const isHidden = parentHidden || hidden.has(menuId);
            const prints = this.printsOf(menuId);
            const hasChildren = Boolean(this.children[menuId]) || prints.length > 0;
            const expanded = filtering || Boolean(this.state.expanded[menuId]);
            const notGiven = depth === 0 && !isHidden && this.notGiven(menuId);
            const info = this.state.appAccess[menuId];
            rows.push({
                id: menuId,
                name: menu.name,
                model: menu.model_label,
                shared: menu.shared,
                depth,
                hidden: isHidden,
                notGiven,
                grant: depth === 0 && info ? info.grant : null,
                parentHidden,
                partial: !isHidden && descendants.some((id) => hidden.has(id)),
                hiddenCount: descendants.filter((id) => hidden.has(id)).length,
                hasChildren,
                expanded,
                selected: this.state.selected === menuId,
                marks: this.marks(menuId),
            });
            if (hasChildren && expanded) {
                const hiddenPrints = new Set(this.state.tree.hidden_prints);
                for (const entry of this.shownPrints(menuId, search, filtering)) {
                    const key = this.printKey(entry);
                    rows.push({
                        id: `${menuId}:${key}`,
                        kind: "print",
                        entry,
                        key,
                        name: entry.label,
                        depth: depth + 1,
                        hidden: hiddenPrints.has(key),
                        icon: entry.kind === "report" ? "print" : "cog",
                    });
                }
                for (const childId of this.children[menuId] || []) {
                    walk(childId, depth + 1, isHidden);
                }
            }
        };
        for (const rootId of this.roots) {
            walk(rootId, 0, false);
        }
        return rows;
    }

    toggleExpand(menuId) {
        this.state.expanded[menuId] = !this.state.expanded[menuId];
        this.keep();
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
        this.keep();
    }

    /** A box of the template: OWL 1 gives the event last. */
    onCheck(method, ...args) {
        const ev = args.pop();
        return this[method](...args, ev.target.checked);
    }

    toggleOnlyRestricted(value) {
        this.state.onlyRestricted = value;
        this.keep();
    }

    /** A change of another field of the form, as Odoo 15 makes it. */
    changeField(name, ids) {
        return new Promise((resolve, reject) => {
            this.trigger("field-changed", {
                dataPointID: this.dataPointId,
                changes: { [name]: { operation: "REPLACE_WITH", ids } },
                viewType: this.viewType,
                onSuccess: resolve,
                onFailure: reject,
            });
        });
    }

    async toggle(menuId, shown) {
        const info = this.state.appAccess[menuId];
        const granted = this.record.data.granted_group_ids;
        if (info && granted) {
            if (shown && this.notGiven(menuId)) {
                // ticking an app its users cannot open gives it to them
                await this.changeField("granted_group_ids", [...granted.res_ids, info.grant.id]);
            } else if (!shown) {
                // unticking an app the profile gives takes it back
                const given = info.group_ids.filter((id) => this.grantedIds.has(id));
                if (given.length) {
                    await this.changeField("granted_group_ids", granted.res_ids.filter((id) => !given.includes(id)));
                }
            }
        }
        const hidden = this.hiddenIds;
        let next;
        if (shown) {
            if (!hidden.has(menuId)) {
                return;
            }
            next = [...hidden].filter((id) => id !== menuId);
        } else {
            // the menu now hides its whole branch: what was hidden below it is redundant
            const below = new Set(this.descendants(menuId));
            next = [...[...hidden].filter((id) => !below.has(id)), menuId];
        }
        return this._setValue({ operation: "REPLACE_WITH", ids: next });
    }

    async togglePrint(entry, shown) {
        if (this.state.busy || !this.ensureSaved({ kind: "print_row", entry, shown })) {
            return;
        }
        this.state.busy = true;
        try {
            await this.call("om_toggle_print", [[this.record.res_id], entry.type, entry.id, !shown]);
            await this.loadTreeState();
            if (this.state.panel) {
                this.state.panel = await this.call("om_menu_panel", [[this.record.res_id], this.state.selected]);
            }
            this.reloadForm();
        } finally {
            this.state.busy = false;
        }
    }

    hiddenLabel(count) {
        return count === 1 ? _t("1 hidden") : sprintf(_t("%s hidden"), count);
    }

    // the panel

    /**
     * The panel writes through the server: the profile must exist and hold
     * the changes made on the form first. Odoo 15 saves through a button of the
     * form, which renders the field again: ``pending`` is run by the new one.
     * Returns whether the profile is saved already.
     */
    ensureSaved(pending) {
        if (this.record.res_id && !this.record.isDirty()) {
            return true;
        }
        this.pending = pending;
        this.keep();
        this.trigger("button-clicked", {
            attrs: { type: "object", name: "om_access_noop" },
            record: this.record,
        });
        return false;
    }

    async runPending(pending) {
        if (pending.kind === "select") {
            return this.select(pending.menuId);
        } else if (pending.kind === "apply") {
            return this.apply(pending.change);
        } else if (pending.kind === "print_row") {
            return this.togglePrint(pending.entry, pending.shown);
        } else if (pending.kind === "rule") {
            return this.openRule();
        }
    }

    /** The other tabs show the lines the panel wrote. */
    reloadForm() {
        this.keep(null);
        this.trigger("reload");
    }

    async select(menuId) {
        this.state.selected = menuId;
        if (!this.ensureSaved({ kind: "select", menuId })) {
            this.state.panel = null;
            return;
        }
        this.state.panel = await this.call("om_menu_panel", [[this.record.res_id], menuId]);
        this.keep();
        if (window.innerWidth < 768) {
            // on a phone the panel sits above the tree
            const panel = this.el.querySelector(".o_om_menu_tree_panel");
            if (panel) {
                panel.scrollIntoView({ block: "start" });
            }
        }
    }

    onApply(ev) {
        ev.stopPropagation();
        return this.apply(ev.detail);
    }

    async apply(change) {
        if (this.state.busy || !this.ensureSaved({ kind: "apply", change })) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.panel = await this.call("om_menu_panel_set", [[this.record.res_id], this.state.selected, change]);
            await this.loadTreeState();
        } finally {
            this.state.busy = false;
        }
        this.reloadForm();
    }

    onOpenRule(ev) {
        ev.stopPropagation();
        return this.openRule();
    }

    async openRule() {
        if (!this.ensureSaved({ kind: "rule" })) {
            return;
        }
        this.state.panel = await this.call("om_menu_panel_set", [[this.record.res_id], this.state.selected,
            { kind: "data_line" }]);
        const lineId = this.state.panel && this.state.panel.line_id;
        if (!lineId) {
            return;
        }
        const action = await this.env.services.rpc({
            model: "om.access.profile.model", method: "action_open_rule", args: [[lineId]],
        });
        this.trigger("do-action", {
            action,
            options: {
                // a rule left at full access goes, as everywhere in the panel
                on_close: () => this.apply({ kind: "data_rights" }),
            },
        });
    }
}

MenuTreeField.template = "om_access_manager.MenuTreeField";
MenuTreeField.components = { MenuPanel };
MenuTreeField.description = _lt("Menu Tree");
MenuTreeField.supportedFieldTypes = ["many2many"];
MenuTreeField.fieldDependencies = {};
// the tree follows the users and the grants of the profile
MenuTreeField.resetOnAnyFieldChange = true;

// Odoo 15 asks the wrapper of an Owl field, which only says yes for
// decorations: let the field say so too
if (!Object.getOwnPropertyDescriptor(FieldWrapper.prototype, "resetOnAnyFieldChange")) {
    Object.defineProperty(FieldWrapper.prototype, "resetOnAnyFieldChange", {
        get() {
            return this.Component.resetOnAnyFieldChange === true;
        },
        configurable: true,
    });
}

fieldRegistry.add("om_access_menu_tree", MenuTreeField);
