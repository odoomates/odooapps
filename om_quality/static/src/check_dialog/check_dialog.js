import { Component, markup, onWillStart, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const MODEL = "om.quality.check";

/**
 * The check screen: the quality checks of a document one after the other, with big buttons
 * for a shop-floor tablet. Pass or fail, measures against their limits, photos from the
 * camera, a note and a failure reason; then what to do with a failed check.
 */
export class QualityCheckDialog extends Component {
    static template = "om_quality.QualityCheckDialog";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const params = this.props.action.params || {};
        this.checkIds = params.check_ids || [];
        this.message = params.message || "";
        this.labels = {
            pass: _t("Pass"),
            fail: _t("Fail"),
            done: _t("Done"),
            record: _t("Record"),
            photo: _t("Take or Add a Photo"),
            removePhoto: _t("Remove this photo"),
            notePlaceholder: _t("What did you see?"),
            valuePlaceholder: _t("Value"),
        };
        this.state = proxy({
            loading: true,
            checks: [],
            reasons: [],
            canOverride: false,
            index: 0,
            busy: false,
            edits: {},
            overrideOpen: false,
            overrideReason: "",
        });
        onWillStart(() => this.load());
    }

    async load(keepIndex = false) {
        const data = await this.orm.call(MODEL, "om_quality_dialog_data", [this.checkIds]);
        this.state.checks = data.checks;
        this.state.reasons = data.reasons;
        this.state.canOverride = data.can_override;
        if (!keepIndex) {
            const firstTodo = data.checks.findIndex((check) => check.state === "todo");
            this.state.index = firstTodo >= 0 ? firstTodo : 0;
        }
        this.state.index = Math.min(this.state.index, Math.max(data.checks.length - 1, 0));
        this.state.edits = {};
        for (const check of data.checks) {
            this.state.edits[check.id] = this.editsFor(check);
        }
        this.state.loading = false;
    }

    editsFor(check) {
        const lines = {};
        for (const line of check.lines) {
            lines[line.id] = { value: line.value_set ? String(line.value) : "", result: line.result };
        }
        return { note: check.note, reasonId: check.reason_id || false, lines };
    }

    get current() {
        return this.state.checks[this.state.index];
    }

    get edit() {
        return this.current && this.state.edits[this.current.id];
    }

    get todoCount() {
        return this.state.checks.filter((check) => check.state === "todo").length;
    }

    html(value) {
        return markup(value || "");
    }

    stateLabel(check) {
        return { todo: _t("To Do"), passed: _t("Passed"), failed: _t("Failed"), cancel: _t("Cancelled") }[check.state];
    }

    stateClass(check) {
        return { todo: check.blocking_pending ? "text-bg-warning" : "text-bg-info", passed: "text-bg-success", failed: "text-bg-danger", cancel: "text-bg-secondary" }[check.state];
    }

    limitsText(line) {
        if (!line.has_limits) {
            return "";
        }
        const unit = line.uom ? ` ${line.uom}` : "";
        return `${line.norm_min} - ${line.norm_max}${unit}`;
    }

    lineStatus(line) {
        const lineEdit = this.edit.lines[line.id];
        if (line.test_kind === "passfail") {
            return lineEdit.result ? (lineEdit.result === "pass" ? "ok" : "ko") : "";
        }
        if (lineEdit.value === "" || lineEdit.value === undefined) {
            return "";
        }
        const value = parseFloat(String(lineEdit.value).replace(",", "."));
        if (Number.isNaN(value)) {
            return "ko";
        }
        if (!line.has_limits) {
            return "ok";
        }
        return value >= line.norm_min && value <= line.norm_max ? "ok" : "ko";
    }

    select(index) {
        this.state.index = index;
        this.state.overrideOpen = false;
    }

    onValue(line, ev) {
        this.edit.lines[line.id].value = ev.target.value;
    }

    setLineResult(line, result) {
        if (this.current.state !== "todo") {
            return;
        }
        this.edit.lines[line.id].result = result;
    }

    onNote(ev) {
        this.edit.note = ev.target.value;
    }

    onReason(ev) {
        this.edit.reasonId = parseInt(ev.target.value) || false;
    }

    async save() {
        const check = this.current;
        if (check.state !== "todo" && check.state !== "failed") {
            return;
        }
        const lines = [];
        if (check.state === "todo") {
            for (const line of check.lines) {
                const lineEdit = this.edit.lines[line.id];
                const value = String(lineEdit.value ?? "").replace(",", ".").trim();
                lines.push({ id: line.id, value: value === "" ? "" : parseFloat(value), result: lineEdit.result || false });
            }
        }
        await this.orm.call(MODEL, "om_quality_dialog_save", [[check.id], {
            note: this.edit.note,
            reason_id: this.edit.reasonId,
            lines,
        }]);
    }

    async run(method, { save = true, advance = false } = {}) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        const checkId = this.current.id;
        try {
            if (save) {
                await this.save();
            }
            const result = await this.orm.call(MODEL, "om_quality_dialog_action", [[checkId], method]);
            if (result) {
                await this.action.doAction(result);
                return;
            }
            await this.load(true);
            const done = this.state.checks.find((check) => check.id === checkId);
            if (advance && done?.state === "passed") {
                const next = this.state.checks.findIndex((check) => check.state === "todo");
                if (next >= 0) {
                    this.state.index = next;
                }
            }
        } finally {
            this.state.busy = false;
        }
    }

    async onPhoto(ev) {
        const files = [...(ev.target.files || [])];
        ev.target.value = "";
        if (!files.length) {
            return;
        }
        const check = this.current;
        this.state.busy = true;
        try {
            for (const file of files) {
                const data = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => resolve(String(reader.result).split(",")[1]);
                    reader.onerror = reject;
                    reader.readAsDataURL(file);
                });
                const photo = await this.orm.call(MODEL, "om_quality_dialog_add_photo", [[check.id], file.name, data]);
                check.photos.push(photo);
            }
        } finally {
            this.state.busy = false;
        }
    }

    async removePhoto(photo) {
        const check = this.current;
        await this.orm.call(MODEL, "om_quality_dialog_remove_photo", [[check.id], photo.id]);
        check.photos = check.photos.filter((p) => p.id !== photo.id);
    }

    onOverrideReason(ev) {
        this.state.overrideReason = ev.target.value;
    }

    async confirmOverride() {
        const reason = this.state.overrideReason.trim();
        if (!reason) {
            this.notification.add(_t("Give the reason of the override."), { type: "warning" });
            return;
        }
        await this.save();
        await this.orm.call(MODEL, "om_quality_dialog_override", [[this.current.id], reason]);
        this.state.overrideOpen = false;
        this.state.overrideReason = "";
        await this.load(true);
    }

    async openForm() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: MODEL,
            res_id: this.current.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    close() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("om_quality_check_dialog", QualityCheckDialog);
