import { Component, markup, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { DomainSelector } from "@web/core/domain_selector/domain_selector";
import { _t } from "@web/core/l10n/translation";
import { ModelFieldSelector } from "@web/core/model_field_selector/model_field_selector";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "approval.rule";
// the sections of the panel, open or not at first: a closed one shows what it holds, and opens on a click
const SECTIONS = {
    button: true, conditions: true, amount: false, requester: false, lock: false, notes: false, advanced: false,
    who: true, mode: true, when: false, followup: true, run: true, record: true,
};
// the buttons listed before "+ more"
const VISIBLE_BUTTONS = 6;
// how long the designer waits after a change before describing the flow again
const PREVIEW_DELAY = 400;

function clone(value) {
    return JSON.parse(JSON.stringify(value));
}

/**
 * The Approval Designer: a flow as a chain of cards, from the button stopped to the button running, with the
 * steps in between. The panel on the right edits the card selected. Each change describes the flow again, in
 * words, below the chain.
 */
export class ApprovalDesigner extends Component {
    static template = "om_approval.Designer";
    static components = { DomainSelector, ModelFieldSelector, MultiRecordSelector, RecordSelector };
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        const params = this.props.action.params || {};
        this.flowId = params.flow_id || false;
        this.model = params.model || false;
        this.state = proxy({
            loaded: false,
            flow: null,
            choices: {},
            preview: { summary: false, conditions: false, steps: [] },
            selected: "trigger",
            dirty: false,
            saving: false,
            advanced: false,
            quick: null,
            quickValue: "",
            // every section is listed: the panel follows the changes of each one
            open: { ...SECTIONS },
            allButtons: false,
        });
        this.previewTimer = null;
        onWillStart(() => this.load());
        onWillUnmount(() => clearTimeout(this.previewTimer));
    }

    async load() {
        this.apply(await this.orm.call(MODEL, "designer_load", [this.flowId, this.model]));
    }

    apply(data) {
        const { flow, preview, ...choices } = data;
        this.flowId = flow.id;
        this.state.flow = flow;
        this.state.choices = choices;
        this.state.preview = preview;
        this.state.dirty = false;
        this.state.loaded = true;
        if (typeof this.state.selected === "number" && this.state.selected >= flow.steps.length) {
            this.state.selected = "trigger";
        }
    }

    // ------------------------------------------------------------------
    // Reading
    // ------------------------------------------------------------------

    get flow() {
        return this.state.flow;
    }

    get isDocument() {
        return this.state.choices.is_document && !this.flow.button_id;
    }

    get button() {
        return this.state.choices.buttons.find((button) => button.id === this.flow.button_id);
    }

    get buttonName() {
        return this.button?.name || _t("the button");
    }

    get texts() {
        return {
            button: _t("Button"),
            conditions: _t("Applies to"),
            amount: _t("Amount"),
            requester: _t("Message to the requester"),
            lock: _t("While it waits"),
            notes: _t("Notes"),
            advanced: _t("Advanced"),
            who: _t("Who approves"),
            mode: _t("How many approve"),
            when: _t("When the step applies"),
            followup: _t("If nobody decides"),
            run: _t("The button"),
            record: _t("The record"),
        };
    }

    isOpen(section) {
        return Boolean(this.state.open[section]);
    }

    toggle(section) {
        this.state.open[section] = !this.state.open[section];
    }

    get visibleButtons() {
        const buttons = this.state.choices.buttons;
        if (this.state.allButtons || buttons.length <= VISIBLE_BUTTONS) {
            return buttons;
        }
        const chosen = buttons.filter((button) => button.id === this.flow.button_id);
        return [...chosen, ...buttons.filter((button) => button.id !== this.flow.button_id)].slice(0, VISIBLE_BUTTONS);
    }

    get hiddenButtonCount() {
        return this.state.choices.buttons.length - this.visibleButtons.length;
    }

    modeLabel(mode) {
        return this.label(this.state.choices.note_modes, mode);
    }

    get buttonValue() {
        if (!this.flow.button_id) {
            return this.state.choices.is_document ? _t("Submit (its own approval)") : _t("Not chosen yet");
        }
        return this.buttonName;
    }

    get conditionsValue() {
        return this.state.preview.conditions ? this.html(this.state.preview.conditions) : _t("Every record");
    }

    get amountValue() {
        return this.flow.amount_field && this.flow.amount_min
            ? _t("Above %s", this.flow.amount_min.toLocaleString())
            : _t("Any amount");
    }

    get requesterValue() {
        return this.flow.note ? this.flow.note : _t("No message");
    }

    get lockValue() {
        if (!this.flow.lock_record) {
            return _t("Not locked");
        }
        return this.flow.lock_after === "keep"
            ? _t("Locked, until an approval manager unlocks it")
            : _t("Locked until %s has run", this.buttonName);
    }

    get notesValue() {
        const parts = this.noteSettings.map(([field]) => this.modeLabel(this.flow[field]));
        return parts.join(" · ");
    }

    get advancedValue() {
        return this.flow.self_approve ? _t("The requester approves their own steps") : _t("Someone else approves");
    }

    get runValue() {
        return this.flow.run_on_approval ? _t("Runs by itself") : _t("Clicked again by the requester");
    }

    modeValue(step) {
        if (step.approval_mode === "count") {
            return _t("%s of them", step.approval_count);
        }
        return this.label(this.state.choices.approval_modes, step.approval_mode);
    }

    whenValue(index) {
        const when = this.stepPreview(index).when;
        return when ? this.html(when) : _t("Always");
    }

    followupValue(step) {
        const parts = [];
        if (step.remind_days) {
            parts.push(_t("reminded after %s d", step.remind_days));
        }
        if (step.escalate_days) {
            parts.push(_t("escalated after %s d", step.escalate_days));
        }
        return parts.length ? parts.join(" · ") : _t("Nothing");
    }

    get noteSettings() {
        const notes = [
            ["approve_note", _t("Approver approves"), "check_circle"],
            ["refuse_note", _t("Approver refuses"), "cancel"],
        ];
        return this.flow.button_id ? [["request_note", _t("Requester asks"), "person"], ...notes] : notes;
    }

    get selectedStep() {
        return typeof this.state.selected === "number" ? this.flow.steps[this.state.selected] : null;
    }

    choiceClass(active) {
        return active ? "o_approval_choice active" : "o_approval_choice";
    }

    html(value) {
        return value ? markup(value) : "";
    }

    label(choices, key) {
        return (choices.find(([value]) => value === key) || [key, key])[1];
    }

    stepPreview(index) {
        return this.state.preview.steps[index] || {};
    }

    triggerProblems() {
        const problems = [];
        if (!(this.flow.name || "").trim()) {
            problems.push(_t("Name the flow."));
        }
        if (!this.flow.button_id && !this.state.choices.is_document) {
            problems.push(_t("Choose the button the flow stops."));
        }
        return problems;
    }

    stepProblems(step) {
        const problems = [];
        if (!(step.name || "").trim()) {
            problems.push(_t("Name the step."));
        }
        if (step.approver_type === "group" && !step.group_id) {
            problems.push(_t("Choose the group approving."));
        }
        if (step.approver_type === "user" && !step.user_ids.length) {
            problems.push(_t("Choose the people approving."));
        }
        if (step.approver_type === "field" && !step.field_path) {
            problems.push(_t("Choose the field naming the approver."));
        }
        if (step.escalate_days && step.escalate_type === "user" && !step.escalate_user_ids.length) {
            problems.push(_t("Choose the people asked when it waits too long."));
        }
        if (step.approval_mode === "count" && !(step.approval_count >= 1)) {
            problems.push(_t("Say how many approve."));
        }
        if (step.escalate_days && step.escalate_type === "group" && !step.escalate_group_id) {
            problems.push(_t("Choose the group asked when it waits too long."));
        }
        return problems;
    }

    hasProblems() {
        return this.triggerProblems().length || this.flow.steps.some((step) => this.stepProblems(step).length);
    }

    // ------------------------------------------------------------------
    // Editing
    // ------------------------------------------------------------------

    changed() {
        this.state.dirty = true;
        clearTimeout(this.previewTimer);
        this.previewTimer = setTimeout(() => this.refreshPreview(), PREVIEW_DELAY);
    }

    async refreshPreview() {
        const flow = clone(this.flow);
        const preview = await this.orm.silent.call(MODEL, "designer_preview", [flow]);
        if (JSON.stringify(flow) === JSON.stringify(this.flow)) {
            this.state.preview = preview;
        }
    }

    set(field, value) {
        this.flow[field] = value;
        this.changed();
    }

    setStep(step, field, value) {
        step[field] = value;
        this.changed();
    }

    setDays(step, field, value) {
        this.setNumber(step, field, value, { integer: true });
    }

    select(key) {
        this.state.selected = key;
        this.state.quick = null;
    }

    addStep(index) {
        const step = clone(this.state.choices.step_defaults);
        step.name = this.flow.steps.length ? _t("Approval %s", index + 1) : _t("Manager");
        this.flow.steps.splice(index, 0, step);
        this.state.selected = index;
        this.changed();
    }

    /** The + between two cards: a step at its place in the chain. */
    insertAt(ev) {
        this.addStep(parseInt(ev.currentTarget.dataset.at, 10));
    }

    removeStep(index) {
        this.flow.steps.splice(index, 1);
        this.state.selected = this.flow.steps.length ? Math.max(0, index - 1) : "trigger";
        this.changed();
    }

    moveStep(index, delta) {
        const target = index + delta;
        if (target < 0 || target >= this.flow.steps.length) {
            return;
        }
        const [step] = this.flow.steps.splice(index, 1);
        this.flow.steps.splice(target, 0, step);
        this.state.selected = target;
        this.changed();
    }

    chooseButton(buttonId) {
        this.flow.button_id = buttonId;
        if (!buttonId) {
            this.flow.lock_record = false;
        }
        this.changed();
    }

    async refreshButtons() {
        const data = await this.orm.call(MODEL, "designer_load", [false, this.flow.model]);
        this.state.choices.buttons = data.buttons;
        this.notification.add(_t("The buttons of %s are listed again.", this.state.choices.model_name), {
            type: "info",
        });
    }

    openQuick(quick) {
        this.state.quick = quick;
        this.state.quickValue = "";
    }

    applyQuick() {
        const value = parseFloat(this.state.quickValue);
        if (Number.isNaN(value)) {
            return;
        }
        const { path, operator, kind } = this.state.quick;
        if (kind === "amount") {
            this.flow.amount_field = path;
            this.set("amount_min", value);
        } else {
            this.set("domain", JSON.stringify([[path, operator, value]]));
        }
        this.state.quick = null;
    }

    setNumber(target, field, value, { integer = false, minimum = 0 } = {}) {
        const number = integer ? parseInt(value, 10) : parseFloat(value);
        target[field] = Math.max(minimum, Number.isNaN(number) ? minimum : number);
        this.changed();
    }

    amountFilter(field) {
        return ["monetary", "float", "integer", "many2one"].includes(field.type);
    }

    clearAmount() {
        this.flow.amount_field = "";
        this.flow.amount_min = 0;
        this.changed();
    }

    stepDomainUpdate(step) {
        return (domain) => this.setStep(step, "domain", domain);
    }

    fieldFilter(field) {
        return field.type === "many2one";
    }

    // ------------------------------------------------------------------
    // Saving
    // ------------------------------------------------------------------

    async save() {
        if (this.state.saving) {
            return false;
        }
        this.state.saving = true;
        try {
            const selected = this.state.selected;
            this.apply(await this.orm.call(MODEL, "designer_save", [this.flowId, clone(this.flow)]));
            this.state.selected = selected;
            this.notification.add(_t("Saved."), { type: "success" });
            return true;
        } finally {
            this.state.saving = false;
        }
    }

    async setActive(active) {
        if (active && this.hasProblems()) {
            this.notification.add(_t("Complete the cards marked in red before activating the flow."), {
                type: "danger",
            });
            return;
        }
        if ((this.state.dirty || !this.flowId) && !(await this.save())) {
            return;
        }
        this.apply(await this.orm.call(MODEL, "designer_set_active", [this.flowId, active]));
        this.notification.add(active ? _t("The flow is active.") : _t("The flow is inactive."), {
            type: active ? "success" : "warning",
        });
    }

    async test() {
        if ((this.state.dirty || !this.flowId) && !(await this.save())) {
            return;
        }
        const action = await this.orm.call(MODEL, "action_simulate", [[this.flowId]]);
        await this.action.doAction(action);
    }

    async openForm() {
        if ((this.state.dirty || !this.flowId) && !(await this.save())) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: this.flowId,
            views: [[false, "form"]],
        });
    }

    close() {
        this.leave(() => this.action.doAction("om_approval.om_approval_flow_action", { clearBreadcrumbs: true }));
    }

    leave(callback) {
        if (!this.state.dirty) {
            callback();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Unsaved Changes"),
            body: _t("Save the changes to the approval flow before leaving?"),
            confirmLabel: _t("Save"),
            confirm: async () => {
                if (await this.save()) {
                    callback();
                }
            },
            cancelLabel: _t("Discard"),
            cancel: () => {
                this.state.dirty = false;
                callback();
            },
        });
    }
}

registry.category("actions").add("om_approval_designer", ApprovalDesigner);
