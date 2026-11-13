import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { DomainSelector } from "@web/core/domain_selector/domain_selector";
import { _t } from "@web/core/l10n/translation";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

import { WorkflowPreview } from "./workflow_preview";

const MODEL = "om.workflow";
const SAVED = "om.workflow.template";

/**
 * The templates of a new workflow: pick a pattern, the model it runs on and
 * its settings, see the chart it draws, and open it in the designer. The
 * templates the company saved start as they were saved.
 */
export class WorkflowTemplateDialog extends Component {
    static template = "om_automation_studio.TemplateDialog";
    static components = { Dialog, DomainSelector, MultiRecordSelector, RecordSelector, WorkflowPreview };
    static props = { close: Function, onBlank: Function };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            templates: [],
            saved: [],
            template: null,
            models: [],
            model: false,
            slots: [],
            values: {},
            name: "",
            preview: null,
            loading: false,
            creating: false,
        });
        this.refresh = useDebounced(() => this.loadPreview(), 250);
        onWillStart(async () => {
            [this.state.templates, this.state.saved] = await Promise.all([
                this.orm.call(MODEL, "template_list", []),
                this.orm.call(SAVED, "gallery_list", []),
            ]);
        });
    }

    title() {
        return this.state.template ? this.state.template.name : _t("New Workflow");
    }

    // ------------------------------------------------------------------
    // steps
    // ------------------------------------------------------------------

    async pick(template) {
        this.state.template = template;
        this.state.models = await this.orm.call(MODEL, "template_models", [template.key]);
        const preset = this.state.models.find((model) => model.preset);
        await this.chooseModel(preset ? preset.model : false);
    }

    async pickSaved(saved) {
        this.state.template = { ...saved, saved: true };
        this.state.model = saved.model;
        this.state.name = saved.name;
        this.state.preview = await this.orm.call(SAVED, "gallery_preview", [[saved.id]]);
    }

    back() {
        this.state.template = null;
        this.state.model = false;
        this.state.slots = [];
        this.state.preview = null;
    }

    blank() {
        this.props.close();
        this.props.onBlank();
    }

    async chooseModel(model) {
        this.state.model = model;
        this.state.preview = null;
        if (!model) {
            this.state.slots = [];
            return;
        }
        this.state.loading = true;
        const setup = await this.orm.call(MODEL, "template_setup", [this.state.template.key, model]);
        this.state.slots = setup.slots;
        this.state.values = setup.values;
        this.state.name = setup.name;
        this.state.loading = false;
        await this.loadPreview();
    }

    async loadPreview() {
        const { template, model, values } = this.state;
        if (!template || !model) {
            return;
        }
        this.state.preview = await this.orm.call(MODEL, "template_preview", [template.key, model, values]);
    }

    async create() {
        this.state.creating = true;
        const template = this.state.template;
        try {
            const action = template.saved
                ? await this.orm.call(SAVED, "create_workflow", [[template.id], this.state.name])
                : await this.orm.call(MODEL, "template_create", [template.key, this.state.model, this.state.values,
                    this.state.name]);
            this.props.close();
            await this.action.doAction(action);
        } finally {
            this.state.creating = false;
        }
    }

    canCreate() {
        const preview = this.state.preview;
        return Boolean(this.state.model && preview?.graph && !preview.missing?.length && !this.state.creating);
    }

    errors() {
        return (this.state.preview?.issues || []).filter((issue) => issue.level === "error");
    }

    // ------------------------------------------------------------------
    // slots
    // ------------------------------------------------------------------

    set(name, value) {
        this.state.values[name] = value;
        // the values of a status belong to the status they were chosen for
        for (const slot of this.state.slots) {
            if (slot.of === name) {
                this.state.values[slot.name] = slot.type === "values" ? [] : false;
            }
        }
        this.refresh();
    }

    slotVisible(slot) {
        if (!slot.of) {
            return true;
        }
        return Boolean(this.state.values[slot.of]);
    }

    /** The field option a slot of type values or value chose its values from. */
    sourceField(slot) {
        const source = this.state.slots.find((other) => other.name === slot.of);
        return source?.options.find((option) => option.name === this.state.values[slot.of]);
    }

    toggleValue(slot, key) {
        const values = [...(this.state.values[slot.name] || [])];
        const index = values.indexOf(key);
        if (index >= 0) {
            values.splice(index, 1);
        } else {
            values.push(key);
        }
        this.set(slot.name, values);
    }

    setUserMode(slot, mode) {
        const current = this.state.values[slot.name] || {};
        if (current.mode === mode) {
            return;
        }
        this.set(slot.name, mode === "field"
            ? { mode, field: slot.options[0]?.name || false }
            : { mode, id: false });
    }

    addField(slot, name) {
        const names = this.state.values[slot.name] || [];
        if (name && !names.includes(name)) {
            this.set(slot.name, [...names, name]);
        }
    }

    removeField(slot, name) {
        this.set(slot.name, (this.state.values[slot.name] || []).filter((other) => other !== name));
    }

    optionLabel(slot, name) {
        return slot.options.find((option) => option.name === name)?.string || name;
    }

    numberValue(ev) {
        const value = parseFloat(ev.target.value);
        return Number.isNaN(value) ? 0 : value;
    }
}
