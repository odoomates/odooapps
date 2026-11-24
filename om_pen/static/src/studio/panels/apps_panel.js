import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { studioSections } from "../studio_action";

export const APP_FEATURES = [
    { key: "stages", label: _t("Stages"), help: _t("A status bar and kanban columns: New, In Progress, Done") },
    { key: "responsible", label: _t("Responsible"), help: _t("The user in charge, the creator by default") },
    { key: "contact", label: _t("Contact"), help: _t("A link to a customer or supplier") },
    { key: "dates", label: _t("Dates"), help: _t("Start and end dates, and a calendar") },
    { key: "amount", label: _t("Amount"), help: _t("An amount in the company currency") },
    { key: "tags", label: _t("Tags"), help: _t("Coloured tags to sort records") },
    { key: "priority", label: _t("Priority"), help: _t("Stars to rank records") },
    { key: "picture", label: _t("Picture"), help: _t("An image on the form and the cards") },
    { key: "lines", label: _t("Lines"), help: _t("A list of lines inside each record") },
    { key: "notes", label: _t("Notes"), help: _t("A notes tab with rich text") },
    { key: "sequence", label: _t("Manual order"), help: _t("Drag records into the order you want") },
    { key: "company", label: _t("Company"), help: _t("For databases with several companies") },
    { key: "chatter", label: _t("Chatter"), help: _t("Messages, followers and history") },
    { key: "activities", label: _t("Activities"), help: _t("Planned calls, meetings and to-dos") },
    { key: "archiving", label: _t("Archiving"), help: _t("Archive records instead of deleting them") },
];

export const ICON_COLORS = ["#5b2b5e", "#1f9d93", "#d9534f", "#f0ad4e", "#337ab7", "#6c757d", "#8e44ad", "#2c3e50"];

/** Create a new app, or a new model in the app on screen. */
export class AppsPanel extends Component {
    static template = "om_pen.AppsPanel";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.menu = useService("menu");
        this.FEATURES = APP_FEATURES;
        this.COLORS = ICON_COLORS;
        this.state = proxy({
            mode: "app",
            app_name: "",
            model_label: "",
            color: ICON_COLORS[1],
            features: ["stages", "responsible", "chatter", "activities"],
            appId: false,
            apps: [],
            saving: false,
        });
        onWillStart(async () => {
            this.state.apps = (await this.orm.call("om.pen.studio", "studio_apps", [])).filter((a) => a.active);
            const info = this.props.store.info;
            if (info?.action) {
                this.state.appId = await this.orm.call("om.pen.studio", "studio_app_of_action", [info.action.id]);
            }
        });
    }

    toggle(key) {
        const index = this.state.features.indexOf(key);
        if (index >= 0) {
            this.state.features.splice(index, 1);
        } else {
            this.state.features.push(key);
        }
    }

    get canCreate() {
        if (this.state.saving) {
            return false;
        }
        return this.state.mode === "app" ? Boolean(this.state.app_name.trim()) : Boolean(this.state.model_label.trim() && this.state.appId);
    }

    async create() {
        this.state.saving = true;
        try {
            const values = {
                app_name: this.state.app_name,
                model_label: this.state.model_label || this.state.app_name,
                color: this.state.color,
                features: [...this.state.features],
            };
            const result = this.state.mode === "app"
                ? await this.orm.call("om.pen.studio", "studio_new_app", [values])
                : await this.orm.call("om.pen.studio", "studio_new_model", [Number(this.state.appId), values]);
            await this.menu.reload();
            await this.props.studio.openModel({ model: result.model, viewType: "form", actionId: result.action_id });
        } finally {
            this.state.saving = false;
        }
    }
}

studioSections.add("apps", { label: _t("New App"), Component: AppsPanel, global: true }, { sequence: 10 });
