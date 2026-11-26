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
        this.dispatch = proxy({ jobs: [], showPanel: true });
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
