import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { CheckBox } from "@web/core/checkbox/checkbox";
import { _t } from "@web/core/l10n/translation";
import { x2ManyCommands } from "@web/core/orm_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { MenuPanel } from "./menu_panel";

const MODEL = "om.access.profile";

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
export class MenuTreeField extends Component {
    static template = "om_access_manager.MenuTreeField";
    static components = { CheckBox, MenuPanel };
    props = useProps({ ...standardFieldProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            expanded: {},
            search: "",
            onlyRestricted: false,
            selected: null,
            panel: null,
            tree: { menu_rules: {}, models: {}, apps: {}, hidden_prints: [] },
            busy: false,
        });
        this.menus = {};
        this.children = {};
        this.roots = [];
        onWillStart(async () => {
            const menus = await this.orm.call(MODEL, "om_menu_tree", []);
            for (const menu of menus) {
                this.menus[menu.id] = menu;
                (this.children[menu.parent_id] ||= []).push(menu.id);
            }
            this.roots = menus.filter((menu) => !menu.parent_id).map((menu) => menu.id);
            this.prints = await this.orm.call(MODEL, "om_tree_prints", []);
            await this.loadTreeState();
        });
    }

    get record() {
        return this.props.record;
    }

    get hiddenIds() {
        return new Set(this.record.data[this.props.name].currentIds);
    }

    async loadTreeState() {
        const resId = this.record.resId;
        this.state.tree = resId
            ? await this.orm.call(MODEL, "om_tree_state", [[resId]])
            : { menu_rules: {}, models: {}, apps: {}, hidden_prints: [] };
    }

    ancestors(menuId) {
        const result = [];
        let parentId = this.menus[menuId]?.parent_id;
        while (parentId) {
            result.push(parentId);
            parentId = this.menus[parentId]?.parent_id;
        }
        return result;
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
            marks.push({ icon: "account_tree", title: rights.length || rule.records !== "all"
                ? _t("Restricts everything below") : _t("Set for everything below") });
        }
        if (this.state.tree.granted_apps?.includes(menuId)) {
            marks.push({ icon: "key", title: _t("Opens the app to its users") });
        }
        if (this.state.tree.apps?.[menuId]) {
            marks.push({ icon: "checklist", title: _t("Only some records allowed in this app") });
        }
        const data = menu.model && this.state.tree.models[menu.model];
        if (data) {
            if (data.rights.some((right) => !right)) {
                marks.push({ icon: "lock", title: data.rights[0]
                    ? _t("Some rights removed") : _t("No access to the data") });
            }
            if (data.records !== "all") {
                marks.push({ icon: "filter_alt", title: _t("Only some records") });
            }
            if (data.fields || data.elements) {
                marks.push({ icon: "visibility_off", title: _t("Fields, tabs or filters hidden") });
            }
            if (data.buttons) {
                marks.push({ icon: "smart_button", title: _t("Buttons hidden or blocked") });
            }
            if (data.print) {
                marks.push({ icon: "print_disabled", title: _t("Reports or actions hidden") });
            }
            if (data.switches) {
                marks.push({ icon: "toggle_off", title: _t("Switches on") });
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
            rows.push({
                id: menuId,
                name: menu.name,
                model: menu.model_label,
                shared: menu.shared,
                depth,
                hidden: isHidden,
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
                        icon: entry.kind === "report" ? "print" : "settings",
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
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
    }

    toggleOnlyRestricted(value) {
        this.state.onlyRestricted = value;
    }

    toggle(menuId, shown) {
        const hidden = this.hiddenIds;
        const commands = [];
        if (shown) {
            if (hidden.has(menuId)) {
                commands.push([x2ManyCommands.UNLINK, menuId]);
            }
        } else {
            const menu = this.menus[menuId];
            commands.push([x2ManyCommands.LINK, menuId, { id: menuId, display_name: menu.name }]);
            // the menu now hides its whole branch: what was hidden below it is redundant
            for (const id of this.descendants(menuId)) {
                if (hidden.has(id)) {
                    commands.push([x2ManyCommands.UNLINK, id]);
                }
            }
        }
        if (commands.length) {
            return this.record.data[this.props.name].applyCommands(commands);
        }
    }

    async togglePrint(entry, shown) {
        if (this.state.busy || !(await this.ensureSaved())) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call(MODEL, "om_toggle_print", [[this.record.resId], entry.type, entry.id, !shown]);
            await this.record.load();
            await this.loadTreeState();
            if (this.state.panel) {
                this.state.panel = await this.orm.call(
                    MODEL, "om_menu_panel", [[this.record.resId], this.state.selected]
                );
            }
        } finally {
            this.state.busy = false;
        }
    }

    hiddenLabel(count) {
        return count === 1 ? _t("1 hidden") : _t("%s hidden", count);
    }

    // the panel

    /** The panel writes through the server: the profile must exist and hold
     * the changes made on the form first. */
    async ensureSaved() {
        if (this.record.isNew || (await this.record.isDirty())) {
            const saved = await this.record.save();
            if (!saved) {
                return false;
            }
        }
        return Boolean(this.record.resId);
    }

    async select(menuId) {
        this.state.selected = menuId;
        if (!(await this.ensureSaved())) {
            this.state.panel = null;
            return;
        }
        this.state.panel = await this.orm.call(MODEL, "om_menu_panel", [[this.record.resId], menuId]);
        if (window.innerWidth < 768) {
            // on a phone the panel sits above the tree
            document.querySelector(".o_om_menu_tree_panel")?.scrollIntoView({ block: "start" });
        }
    }

    async apply(change) {
        if (this.state.busy || !(await this.ensureSaved())) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.panel = await this.orm.call(
                MODEL, "om_menu_panel_set", [[this.record.resId], this.state.selected, change]
            );
            // the other tabs show the same lines
            await this.record.load();
            await this.loadTreeState();
        } finally {
            this.state.busy = false;
        }
    }

    async openRule() {
        await this.apply({ kind: "data_line" });
        const lineId = this.state.panel?.line_id;
        if (!lineId) {
            return;
        }
        const action = await this.orm.call("om.access.profile.model", "action_open_rule", [[lineId]]);
        await this.action.doAction(action, {
            // a rule left at full access goes, as everywhere in the panel
            onClose: () => this.apply({ kind: "data_rights" }),
        });
    }
}

export const menuTreeField = {
    component: MenuTreeField,
    displayName: _t("Menu Tree"),
    supportedTypes: ["many2many"],
    relatedFields: () => [{ name: "display_name", type: "char" }],
    isEmpty: () => false,
};

registry.category("fields").add("om_access_menu_tree", menuTreeField);
