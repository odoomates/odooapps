import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { SignatureDialog } from "@web/core/signature/signature_dialog";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const { DateTime } = luxon;

const STATE_CLASSES = {
    new: "text-bg-light border",
    planned: "text-bg-primary",
    travelling: "text-bg-info",
    in_progress: "text-bg-warning",
    waiting_parts: "text-bg-danger",
    done: "text-bg-success",
    cancelled: "text-bg-secondary",
};

/**
 * Read a picture and make it at most ``maxSize`` pixels wide or high (JPEG).
 *
 * @param {File} file
 * @param {number} maxSize
 * @returns {Promise<string>} base64 content, without the data URL prefix
 */
export function readPicture(file, maxSize = 1600) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(reader.error);
        reader.onload = () => {
            const image = new Image();
            image.onerror = () => resolve(reader.result.split(",")[1]);
            image.onload = () => {
                const ratio = Math.min(1, maxSize / Math.max(image.width, image.height));
                const canvas = document.createElement("canvas");
                canvas.width = Math.round(image.width * ratio);
                canvas.height = Math.round(image.height * ratio);
                canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
                resolve(canvas.toDataURL("image/jpeg", 0.85).split(",")[1]);
            };
            image.src = reader.result;
        };
        reader.readAsDataURL(file);
    });
}

/**
 * Phone screen of the technician: the jobs of the day in order, and for a job the way to the
 * site, the travel and work timers, the checklist, notes, photos, the customer signature and
 * the end of the job with its report.
 */
export class FieldServiceTechnician extends Component {
    static template = "om_field_service.Technician";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.stateClasses = STATE_CLASSES;
        const params = this.props.action.params || {};
        this.state = proxy({
            day: DateTime.local().toISODate(),
            jobs: [],
            job: null,
            busy: false,
            now: DateTime.now(),
            notes: "",
            notesDirty: false,
        });
        onWillStart(async () => {
            await this.loadJobs();
            if (params.job_id) {
                await this.openJob(params.job_id);
            }
        });
        this.interval = setInterval(() => (this.state.now = DateTime.now()), 1000);
        onWillUnmount(() => clearInterval(this.interval));
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------

    async loadJobs() {
        const data = await this.orm.call("project.task", "fs_mobile_jobs", [this.state.day]);
        this.state.jobs = data.jobs;
    }

    setJob(data) {
        this.state.job = data;
        this.state.notes = data.notes;
        this.state.notesDirty = false;
    }

    async openJob(jobId) {
        this.setJob(await this.orm.call("project.task", "fs_mobile_job", [[jobId]]));
        window.scrollTo?.(0, 0);
    }

    async reloadJob() {
        if (this.state.job) {
            await this.openJob(this.state.job.id);
        }
    }

    async back() {
        await this.saveNotes();
        this.state.job = null;
        await this.loadJobs();
    }

    async changeDay(delta) {
        const day = delta ? DateTime.fromISO(this.state.day).plus({ days: delta }) : DateTime.local();
        this.state.day = day.toISODate();
        await this.loadJobs();
    }

    async run(callback) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await callback();
        } finally {
            this.state.busy = false;
        }
    }

    // ------------------------------------------------------------------
    // Formatting
    // ------------------------------------------------------------------

    get dayLabel() {
        const day = DateTime.fromISO(this.state.day);
        if (day.hasSame(DateTime.local(), "day")) {
            return _t("Today");
        }
        return day.toLocaleString({ weekday: "long", day: "numeric", month: "long" });
    }

    toLocal(value) {
        return value ? DateTime.fromSQL(value, { zone: "utc" }).toLocal() : null;
    }

    formatTime(value) {
        const date = this.toLocal(value);
        return date ? date.toLocaleString(DateTime.TIME_SIMPLE) : "";
    }

    formatPeriod(job) {
        if (!job.start) {
            return _t("Not planned");
        }
        const start = this.toLocal(job.start);
        let label = `${start.toLocaleString(DateTime.TIME_SIMPLE)}`;
        if (job.end) {
            label += ` - ${this.formatTime(job.end)}`;
        }
        if (!start.hasSame(DateTime.fromISO(this.state.day), "day")) {
            label = `${start.toLocaleString({ day: "numeric", month: "short" })} ${label}`;
        }
        return label;
    }

    formatHours(hours) {
        const minutes = Math.round((hours || 0) * 60);
        return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
    }

    get timerLabel() {
        const start = this.toLocal(this.state.job?.timer_start);
        if (!start) {
            return "";
        }
        const seconds = Math.max(0, Math.floor(this.state.now.diff(start, "seconds").seconds));
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    get checklistDone() {
        const lines = this.state.job?.checklist || [];
        return lines.filter((line) => line.done).length;
    }

    photoUrl(photo) {
        return `/web/image/${photo.id}/256x256?unique=${photo.id}`;
    }

    get signatureUrl() {
        const job = this.state.job;
        return `/web/image/project.task/${job.id}/customer_signature?unique=${encodeURIComponent(job.signed_on || "")}`;
    }

    get reportUrl() {
        return `/report/pdf/om_field_service.report_fs_job/${this.state.job.id}`;
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------

    async doAction(name) {
        await this.run(async () => {
            if (name === "done") {
                await this.saveNotes();
            }
            this.setJob(await this.orm.call("project.task", "fs_mobile_action", [[this.state.job.id], name]));
            if (name === "done") {
                this.notification.add(_t("Job done. The report is sent to the customer."), { type: "success" });
            }
        });
    }

    async saveChecklist(line, values) {
        await this.orm.write("om.fs.checklist.line", [line.id], values);
        await this.reloadJob();
    }

    onToggleCheck(line) {
        return this.saveChecklist(line, { value_check: !line.check });
    }

    onChangeText(line, ev) {
        return this.saveChecklist(line, { value_text: ev.target.value });
    }

    onChangeNumber(line, ev) {
        const raw = ev.target.value;
        if (raw === "") {
            return this.saveChecklist(line, { value_number: 0, value_number_set: false });
        }
        return this.saveChecklist(line, { value_number: parseFloat(raw), value_number_set: true });
    }

    onNotesInput(ev) {
        this.state.notes = ev.target.value;
        this.state.notesDirty = true;
    }

    async saveNotes() {
        if (!this.state.job || !this.state.notesDirty) {
            return;
        }
        await this.orm.call("project.task", "fs_mobile_set_notes", [[this.state.job.id], this.state.notes]);
        this.state.notesDirty = false;
    }

    async onPhotoSelected(ev) {
        const files = [...(ev.target.files || [])];
        ev.target.value = "";
        if (!files.length) {
            return;
        }
        await this.run(async () => {
            for (const file of files) {
                const data = await readPicture(file);
                this.setJob(
                    await this.orm.call("project.task", "fs_mobile_add_photo", [
                        [this.state.job.id],
                        file.name || _t("Photo"),
                        data,
                    ])
                );
            }
        });
    }

    async removePhoto(photo) {
        await this.run(async () => {
            this.setJob(
                await this.orm.call("project.task", "fs_mobile_remove_photo", [[this.state.job.id], photo.id])
            );
        });
    }

    openSignature() {
        const job = this.state.job;
        this.dialog.add(SignatureDialog, {
            defaultName: job.contact || job.customer,
            nameAndSignatureProps: {
                mode: "draw",
                displaySignatureRatio: 2,
                signatureType: "signature",
                noInputName: false,
            },
            uploadSignature: ({ name, signatureImage }) =>
                this.run(async () => {
                    this.setJob(
                        await this.orm.call("project.task", "fs_mobile_sign", [
                            [job.id],
                            name,
                            signatureImage.split(",")[1],
                        ])
                    );
                }),
        });
    }

    async sendReport() {
        await this.run(async () => {
            await this.orm.call("project.task", "fs_mobile_send_report", [[this.state.job.id]]);
            this.notification.add(_t("The report was sent to the customer."), { type: "success" });
        });
    }

    openForm() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: this.state.job.id,
            views: [[false, "form"]],
            context: { form_view_ref: "om_field_service.project_task_view_form_fs", om_fs_job: true },
        });
    }
}

registry.category("actions").add("om_fs_technician", FieldServiceTechnician);
