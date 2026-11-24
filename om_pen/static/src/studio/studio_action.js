import { Component, onWillStart, onWillUnmount, proxy, useProps, useListener } from "@odoo/owl";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpcBus } from "@web/core/network/rpc";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { StudioStore } from "./store";
import { StudioCanvas } from "./canvas";
import { StudioSidebar } from "./sidebar";
import {
    HeaderButtonDialog,
    NewFieldDialog,
    RibbonDialog,
    SmartButtonDialog,
    VersionsDialog,
} from "./dialogs";
import { NEW_FIELD_KINDS } from "./sidebar";

export const VIEW_TYPE_INFO = {
    form: { label: _t("Form"), icon: "description" },
    list: { label: _t("List"), icon: "list" },
    kanban: { label: _t("Kanban"), icon: "view_kanban" },
    calendar: { label: _t("Calendar"), icon: "calendar_month" },
    pivot: { label: _t("Pivot"), icon: "table_chart" },
    graph: { label: _t("Graph"), icon: "bar_chart" },
    activity: { label: _t("Activity"), icon: "schedule" },
    search: { label: _t("Search"), icon: "search" },
};

/**
 * The sections of the top bar besides the views. Each one is a component taking the
 * store; they are registered by the files that implement them.
 */
export const studioSections = registry.category("om_pen.studio_sections");

export class StudioAction extends Component {
    static template = "om_pen.StudioAction";
    static components = { StudioCanvas, StudioSidebar };
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.notification = useService("notification");
        this.store = new StudioStore({ orm: this.orm, notification: this.notification });
        this.params = this.props.action.params || {};
        this.ui = proxy({ firstResId: false, viewTypes: [] });
        this.VIEW_TYPE_INFO = VIEW_TYPE_INFO;

        onWillStart(async () => {
            const params = this.params;
            if (!params.model) {
                // nothing to customize on the screen the Studio was opened from
                this.store.state.section = "apps";
                return;
            }
            await this.store.open(params);
            await this.loadFirstRecord();
            this.computeViewTypes();
        });

        useListener(document, "keydown", (ev) => this.onKeydown(ev));
        // what is created while the Studio is open is marked as the Studio's work
        user.updateContext({ om_pen_studio: true });
        onWillUnmount(() => user.updateContext({ om_pen_studio: false }));
    }

    async loadFirstRecord() {
        if (this.store.state.resId || !this.store.info) {
            return;
        }
        const ids = await this.orm.search(this.store.info.model, [], { limit: 1 });
        this.ui.firstResId = ids[0] || false;
    }

    computeViewTypes() {
        const info = this.store.info;
        const fromAction = info.action?.view_types?.length ? info.action.view_types : [info.view_type];
        const types = fromAction.filter((t) => VIEW_TYPE_INFO[t]);
        if (!types.includes(info.view_type)) {
            types.push(info.view_type);
        }
        if (!types.includes("search")) {
            types.push("search");
        }
        this.ui.viewTypes = types;
    }

    get missingViewTypes() {
        if (!this.store.info?.action) {
            return [];
        }
        return Object.keys(VIEW_TYPE_INFO).filter(
            (t) => !this.ui.viewTypes.includes(t) && (t !== "activity" || this.store.info.has_chatter)
        );
    }

    get sections() {
        return studioSections.getEntries().map(([key, section]) => ({ key, ...section }));
    }

    get sectionComponent() {
        const key = this.store.state.section;
        return key === "views" ? null : studioSections.get(key, null)?.Component;
    }

    onKeydown(ev) {
        const mod = ev.ctrlKey || ev.metaKey;
        if (!mod || this.store.state.section !== "views" || ["INPUT", "TEXTAREA", "SELECT"].includes(ev.target.tagName)) {
            return;
        }
        if (ev.key === "z" && !ev.shiftKey && this.store.view?.can_undo) {
            ev.preventDefault();
            this.store.undo();
        } else if ((ev.key === "y" || (ev.key === "z" && ev.shiftKey)) && this.store.view?.can_redo) {
            ev.preventDefault();
            this.store.redo();
        }
    }

    /** Start editing another model, such as one just created in the app builder. */
    async openModel(params) {
        this.store.state.selected = null;
        this.store.state.resId = false;
        this.ui.firstResId = false;
        await this.store.open(params);
        await this.loadFirstRecord();
        this.computeViewTypes();
        this.store.state.section = "views";
    }

    async switchView(viewType) {
        await this.store.switchView(viewType);
        this.store.state.section = "views";
    }

    async addViewType(viewType) {
        await this.orm.call("om.pen.studio", "studio_action_add_view", [this.store.info.action.id, viewType]);
        this.store.info.action.view_types.push(viewType);
        this.computeViewTypes();
        await this.switchView(viewType);
    }

    // ------------------------------------------------------------------
    // dropping from the panel
    // ------------------------------------------------------------------

    async onDrop(drag, target, position) {
        const store = this.store;
        if (drag.kind === "move") {
            return store.move(drag.node, target, position);
        }
        if (drag.kind === "existing" || drag.kind === "component") {
            return store.insert(target, position, drag.element);
        }
        if (drag.kind === "new") {
            const kind = NEW_FIELD_KINDS.find((k) => k.kind === drag.fieldKind);
            const model = drag.model || store.info.model;
            const fields = model === store.info.model ? store.view.all_fields : store.view.related_models[model]?.fields || {};
            this.dialog.add(NewFieldDialog, {
                kind: drag.fieldKind,
                label: kind?.label || drag.fieldKind,
                model,
                fields,
                onConfirm: async (values) => {
                    await store.call("studio_create_field", [store.view.revision, values, target, position, store.state.showHidden]);
                    // the model changed: the web client has to load its fields again
                    rpcBus.trigger("CLEAR-CACHES", "get_views");
                },
            });
        }
    }

    onSpecial(key) {
        const store = this.store;
        const revision = () => store.view.revision;
        const hidden = () => store.state.showHidden;
        if (key === "ribbon") {
            const sheet = store.findNode((n) => n.tag === "sheet") ?? store.rootId;
            this.dialog.add(RibbonDialog, {
                onConfirm: (values) => store.insert(sheet, "inside", { kind: "ribbon", ...values }),
            });
        } else if (key === "smart_button") {
            this.dialog.add(SmartButtonDialog, {
                model: store.info.model,
                onConfirm: (values) => store.call("studio_add_smart_button", [revision(), values, hidden()]),
            });
        } else if (key === "header_button") {
            this.dialog.add(HeaderButtonDialog, {
                model: store.info.model,
                fields: store.view.all_fields,
                onConfirm: (values) => store.call("studio_add_header_button", [revision(), values, hidden()]),
            });
        } else if (key === "stages") {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Add stages"),
                body: _t(
                    "This adds a Stage field with the stages New, In Progress and Done, a status bar on the form, and groups the kanban by stage. Stages can be renamed and added afterwards."
                ),
                confirmLabel: _t("Add stages"),
                confirm: () => store.call("studio_add_stages", [revision(), hidden()]),
                cancel: () => {},
            });
        } else if (key === "chatter") {
            store.call("studio_enable_chatter", [revision(), hidden()]);
        }
    }

    // ------------------------------------------------------------------
    // top bar
    // ------------------------------------------------------------------

    openVersions() {
        this.dialog.add(VersionsDialog, {
            customizationId: this.store.info.customization_id,
            onRestore: (versionId) => this.store._run("studio_version_restore", [versionId, this.store.state.showHidden]),
        });
    }

    confirmDiscard() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Discard unpublished changes"),
            body: _t("Everything not yet published on this view is thrown away. What is live stays as it is."),
            confirmLabel: _t("Discard"),
            confirmClass: "btn-danger",
            confirm: () => this.store.discard(),
            cancel: () => {},
        });
    }

    async close() {
        const leave = async () => {
            rpcBus.trigger("CLEAR-CACHES", "get_views");
            const info = this.store.info;
            if (info?.action?.id) {
                const viewType = info.view_type === "search" ? undefined : info.view_type;
                const options = { clearBreadcrumbs: true };
                if (viewType) {
                    options.viewType = viewType;
                }
                if (viewType === "form" && this.store.state.resId) {
                    options.props = { resId: this.store.state.resId };
                }
                await this.action.doAction(info.action.id, options);
            } else {
                await this.action.doAction("home");
            }
        };
        if (this.store.view?.has_draft) {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Unpublished changes"),
                body: _t(
                    "This view has changes nobody else sees yet. They are kept as a draft: open the Studio again to publish them."
                ),
                confirmLabel: _t("Leave"),
                confirm: leave,
                cancel: () => {},
            });
            return;
        }
        await leave();
    }
}

registry.category("actions").add("om_pen.studio", StudioAction);
