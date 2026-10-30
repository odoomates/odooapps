import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { ModelSelector } from "@web/core/model_selector/model_selector";
import { useService } from "@web/core/utils/hooks";

const MODEL = "approval.rule";

/**
 * New approval flow: a template and the kind of record it applies to, or a blank flow. The flow is created
 * inactive and opens in the Approval Designer.
 */
export class ApprovalGalleryDialog extends Component {
    static template = "om_approval.GalleryDialog";
    static components = { Dialog, ModelSelector };
    props = useProps({ close: t.function(), model: t.string().optional(), prefix: t.string().optional() });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ templates: [], template: null, model: this.props.model || false, modelName: "",
                             busy: false });
        onWillStart(async () => {
            const data = await this.orm.call(MODEL, "gallery_load", [this.props.model || false,
                                                                      this.props.prefix || false]);
            this.state.templates = this.props.model
                ? data.templates.filter((template) => template.models.some((m) => m.model === this.props.model))
                : data.templates;
        });
    }

    get title() {
        return this.state.template ? this.state.template.name : _t("New Approval Flow");
    }

    pick(template) {
        this.state.template = template;
        const ready = template.models || [];
        const chosen = ready.find((m) => m.model === this.state.model);
        if (!chosen && !this.props.model) {
            this.state.model = ready.length === 1 ? ready[0].model : false;
        }
        this.state.modelName = (ready.find((m) => m.model === this.state.model) || {}).name || "";
    }

    blank() {
        this.pick({ key: "blank", name: _t("Start from blank"), blank: true, models: [],
                    description: _t("A button, and the steps you add.") });
    }

    back() {
        this.state.template = null;
        this.state.model = this.props.model || false;
    }

    chooseModel(model, name) {
        this.state.model = model;
        this.state.modelName = name;
    }

    async create() {
        if (!this.state.model || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const params = this.state.template.blank
                ? { model: this.state.model }
                : { flow_id: await this.orm.call(MODEL, "gallery_create", [this.state.template.key, this.state.model]) };
            this.props.close();
            await this.action.doAction({ type: "ir.actions.client", tag: "om_approval_designer", params });
        } finally {
            this.state.busy = false;
        }
    }
}
