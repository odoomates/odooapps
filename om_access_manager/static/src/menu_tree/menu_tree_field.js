import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { CheckBox } from "@web/core/checkbox/checkbox";
import { _t } from "@web/core/l10n/translation";
import { x2ManyCommands } from "@web/core/orm_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * The hidden menus of an access profile, shown as the real menu tree: a ticked
 * menu is shown, an unticked one is hidden with everything below it.
 *
 * The field stays a plain many2many of the hidden menus, and only the topmost
 * hidden menu of a branch is kept in it: the engine hides the children of a
 * hidden menu on its own.
 */
export class MenuTreeField extends Component {
    static template = "om_access_manager.MenuTreeField";
    static components = { CheckBox };
    props = useProps({ ...standardFieldProps });

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ expanded: {}, search: "" });
        this.menus = {};
        this.children = {};
        this.roots = [];
        onWillStart(async () => {
            const menus = await this.orm.call("om.access.profile", "om_menu_tree", []);
            for (const menu of menus) {
                this.menus[menu.id] = menu;
                (this.children[menu.parent_id] ||= []).push(menu.id);
            }
            this.roots = menus.filter((menu) => !menu.parent_id).map((menu) => menu.id);
        });
    }

    get hiddenIds() {
        return new Set(this.props.record.data[this.props.name].currentIds);
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

    matches(menuId, search) {
        if (this.menus[menuId].name.toLowerCase().includes(search)) {
            return true;
        }
        return (this.children[menuId] || []).some((id) => this.matches(id, search));
    }

    /**
     * The rows on screen, depth first. A search shows every branch holding a
     * match, unfolded.
     */
    get rows() {
        const hidden = this.hiddenIds;
        const search = this.state.search.trim().toLowerCase();
        const rows = [];
        const walk = (menuId, depth, parentHidden) => {
            if (search && !this.matches(menuId, search)) {
                return;
            }
            const descendants = this.descendants(menuId);
            const isHidden = parentHidden || hidden.has(menuId);
            const hasChildren = Boolean(this.children[menuId]);
            const expanded = Boolean(search) || Boolean(this.state.expanded[menuId]);
            rows.push({
                id: menuId,
                name: this.menus[menuId].name,
                depth,
                hidden: isHidden,
                parentHidden,
                partial: !isHidden && descendants.some((id) => hidden.has(id)),
                hiddenCount: descendants.filter((id) => hidden.has(id)).length,
                hasChildren,
                expanded,
            });
            if (hasChildren && expanded) {
                for (const childId of this.children[menuId]) {
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
            return this.props.record.data[this.props.name].applyCommands(commands);
        }
    }

    hiddenLabel(count) {
        return count === 1 ? _t("1 hidden") : _t("%s hidden", count);
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
