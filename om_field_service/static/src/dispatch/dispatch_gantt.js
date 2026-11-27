import { onWillStart, proxy } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { PlanningGanttController, planningGanttView } from "@om_planning/planning_gantt";

const UNPLANNED_DOMAIN = [
    ["is_field_service", "=", true],
    ["planned_start", "=", false],
    ["job_state", "not in", ["done", "cancelled"]],
];

/**
 * Dispatch Gantt: the planning slots of the jobs by technician, with the jobs to plan on the
 * side. A job is planned from its card (free technicians suggested) or with the search button
 * of a cell (first free time of the technician of the row in the cell).
 */
export class DispatchGanttController extends PlanningGanttController {
    static template = "om_field_service.DispatchGanttController";

    setup() {
        super.setup();
        this.dispatch = proxy({ jobs: [], showPanel: true, dragJob: null });
        onWillStart(() => this.loadJobs());
    }

    async loadJobs() {
        this.dispatch.jobs = await this.orm.call("om.planning.slot", "fs_unplanned_jobs", []);
    }

    async reload() {
        await Promise.all([this.model.load(), this.loadJobs()]);
    }

    togglePanel() {
        this.dispatch.showPanel = !this.dispatch.showPanel;
    }

    async planJob(job) {
        const action = await this.orm.call("project.task", "action_fs_plan", [[job.id]]);
        await this.actionService.doAction(action, { onClose: () => this.reload() });
    }

    openJob(jobId) {
        this.addDialog(FormViewDialog, {
            resModel: "project.task",
            resId: jobId,
            context: { form_view_ref: "om_field_service.project_task_view_form_fs", om_fs_job: true },
            title: _t("Job"),
            onRecordSaved: () => this.reload(),
        });
    }

    openRecord(record) {
        const job = record.raw && record.raw.fs_job_id;
        if (job && job.id) {
            this.openJob(job.id);
            return;
        }
        super.openRecord(record);
    }

    planRecords(params) {
        if (!this.model.canWrite) {
            return;
        }
        const defaults = this.model.getContextDefaults(params);
        this.addDialog(SelectCreateDialog, {
            resModel: "project.task",
            title: _t("Plan jobs here"),
            domain: UNPLANNED_DOMAIN,
            context: { list_view_ref: "om_field_service.project_task_view_list_fs" },
            noCreate: true,
            onSelected: async (resIds) => {
                if (!resIds.length) {
                    return;
                }
                const count = await this.orm.call("om.planning.slot", "fs_plan_jobs", [resIds, defaults]);
                this.notification.add(_t("%s jobs planned.", count), { type: "success" });
                await this.reload();
            },
        });
    }

    openMap() {
        this.actionService.doAction("om_field_service.action_om_fs_map");
    }

    openRoutes() {
        const range = this.model.data.range;
        this.actionService.doAction("om_field_service.action_om_fs_route_wizard", {
            additionalContext: { default_date: range.start.toISODate() },
            onClose: () => this.reload(),
        });
    }

    // ------------------------------------------------------------------
    // Drag a job of the side panel onto a technician at a time
    // ------------------------------------------------------------------

    onJobDragStart(ev, job) {
        if (!this.model.canWrite) {
            ev.preventDefault();
            return;
        }
        ev.dataTransfer.setData("application/x-om-fs-job", String(job.id));
        ev.dataTransfer.effectAllowed = "move";
        this.dispatch.dragJob = job;
    }

    onJobDragEnd() {
        this.dispatch.dragJob = null;
        this.clearDropTarget();
    }

    clearDropTarget() {
        for (const el of document.querySelectorAll(".o_fs_drop_target")) {
            el.classList.remove("o_fs_drop_target");
        }
    }

    findRow(key) {
        const search = (rows) => {
            for (const row of rows) {
                if (row.key === key) {
                    return row;
                }
                const found = search(row.children || []);
                if (found) {
                    return found;
                }
            }
            return null;
        };
        return search(this.model.data.rows);
    }

    /**
     * The row and the time under the pointer.
     *
     * @returns {{ row: Object, start: luxon.DateTime, stop: luxon.DateTime, el: HTMLElement } | null}
     */
    dropTargetAt(ev) {
        const rowEl = ev.target.closest?.(".o_gantt_row[data-row-key]");
        const contentEl = rowEl?.querySelector(".o_gantt_row_content");
        if (!contentEl) {
            return null;
        }
        const row = this.findRow(rowEl.dataset.rowKey);
        if (!row || row.isGroup) {
            return null;
        }
        const rect = contentEl.getBoundingClientRect();
        const columns = this.model.data.columns;
        const position = Math.max(0, Math.min(columns.length - 1e-6, ((ev.clientX - rect.left) / rect.width) * columns.length));
        const column = columns[Math.floor(position)];
        let start = this.model.positionToDate(position);
        if (start >= column.stop) {
            start = column.start;
        }
        return { row, start, stop: column.stop, el: rowEl };
    }

    onDragOver(ev) {
        if (!this.dispatch.dragJob) {
            return;
        }
        const target = this.dropTargetAt(ev);
        if (!target) {
            this.clearDropTarget();
            return;
        }
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        if (!target.el.classList.contains("o_fs_drop_target")) {
            this.clearDropTarget();
            target.el.classList.add("o_fs_drop_target");
        }
    }

    onDragLeave(ev) {
        if (!ev.currentTarget.contains(ev.relatedTarget)) {
            this.clearDropTarget();
        }
    }

    async onDrop(ev) {
        const job = this.dispatch.dragJob;
        const target = job && this.dropTargetAt(ev);
        this.onJobDragEnd();
        if (!target) {
            return;
        }
        ev.preventDefault();
        // day scale: the job starts where it is dropped; other scales: first free time that day
        const exact = this.model.scale === "day";
        const stop = exact ? target.start.plus({ minutes: Math.round(job.duration * 60) }) : target.stop;
        const defaults = this.model.getContextDefaults({ start: target.start, stop, row: target.row });
        const count = await this.orm.call("om.planning.slot", "fs_plan_jobs", [[job.id], defaults], { exact });
        if (count) {
            this.notification.add(_t("%s planned.", job.number || job.name), { type: "success" });
        }
        await this.reload();
    }

    priorityStars(job) {
        return Number(job.priority || 0);
    }

    formatDeadline(job) {
        if (!job.deadline) {
            return "";
        }
        return luxon.DateTime.fromSQL(job.deadline, { zone: "utc" }).toLocal().toLocaleString(luxon.DateTime.DATE_MED);
    }

    formatDuration(hours) {
        const minutes = Math.round(hours * 60);
        return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
    }
}

export const dispatchGanttView = {
    ...planningGanttView,
    Controller: DispatchGanttController,
    buttonTemplate: "om_field_service.DispatchGanttButtons",
};

registry.category("views").add("om_fs_dispatch_gantt", dispatchGanttView);
