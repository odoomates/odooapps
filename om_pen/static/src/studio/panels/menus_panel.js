import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { studioSections } from "../studio_action";
import { APP_FEATURES } from "./apps_panel";

/** A new menu: a folder, an existing action, or a new model with its views. */
export class NewMenuDialog extends Component {
    static template = "om_pen.NewMenuDialog";
    static components = { Dialog };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.FEATURES = APP_FEATURES;
        this.state = proxy({ name: "", kind: "model", action_id: "", features: ["responsible", "chatter"], actions: [] });
        onWillStart(async () => {
            this.state.actions = await this.orm.call("om.pen.studio", "studio_window_actions", []);
        });
    }

    toggle(key) {
        const index = this.state.features.indexOf(key);
        index >= 0 ? this.state.features.splice(index, 1) : this.state.features.push(key);
    }

    async confirm() {
        await this.orm.call("om.pen.studio", "studio_menu_create", [
            this.props.parentId,
            {
                name: this.state.name,
                kind: this.state.kind,
                action_id: Number(this.state.action_id) || false,
                features: [...this.state.features],
            },
        ]);
        await this.props.onDone();
        this.props.close();
    }
}

/** The menus of an app: rename, reorder, hide, add and delete them. */
export class MenusPanel extends Component {
    static template = "om_pen.MenusPanel";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.menu = useService("menu");
        this.dialog = useService("dialog");
        this.state = proxy({ apps: [], appId: false, tree: null, editing: null });
        onWillStart(async () => {
            this.state.apps = await this.orm.call("om.pen.studio", "studio_apps", []);
            const info = this.props.store.info;
            let appId = false;
            if (info?.action) {
                appId = await this.orm.call("om.pen.studio", "studio_app_of_action", [info.action.id]);
            }
            this.state.appId = appId || this.state.apps[0]?.id || false;
            await this.load();
        });
    }

    async load() {
        this.state.tree = this.state.appId
            ? await this.orm.call("om.pen.studio", "studio_menus", [Number(this.state.appId)])
            : null;
    }

    get rows() {
        const rows = [];
        const walk = (node) => {
            rows.push(node);
            node.children.forEach(walk);
        };
        if (this.state.tree) {
            walk(this.state.tree);
        }
        return rows;
    }

    async onAppChange(ev) {
        this.state.appId = Number(ev.target.value);
        await this.load();
    }

    async update(menu, values) {
        await this.orm.call("om.pen.studio", "studio_menu_update", [menu.id, values]);
        await this.load();
        await this.menu.reload();
    }

    async rename(menu, ev) {
        this.state.editing = null;
        const name = ev.target.value.trim();
        if (name && name !== menu.name) {
            await this.update(menu, { name });
        }
    }

    addMenu(parent) {
        this.dialog.add(NewMenuDialog, {
            parentId: parent.id,
            onDone: async () => {
                await this.load();
                await this.menu.reload();
            },
        });
    }

    deleteMenu(menu) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete a menu"),
            body: _t("Delete the menu %s and the menus under it? What they open is kept.", menu.name),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.orm.call("om.pen.studio", "studio_menu_delete", [menu.id]);
                await this.load();
                await this.menu.reload();
            },
            cancel: () => {},
        });
    }

    async editViews(menu) {
        await this.props.studio.openModel({ model: menu.model, viewType: "list", actionId: menu.action_id });
    }
}

studioSections.add("menus", { label: _t("Menus"), Component: MenusPanel }, { sequence: 20 });
