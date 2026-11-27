import { patch } from "@web/core/utils/patch";
import { FieldServiceTechnician } from "@om_field_service/technician/technician";

const QUALITY_CLASSES = {
    todo: "text-bg-warning",
    passed: "text-bg-success",
    failed: "text-bg-danger",
    cancel: "text-bg-secondary",
};

patch(FieldServiceTechnician.prototype, {
    qualityClass(check) {
        return QUALITY_CLASSES[check.state] || "text-bg-light";
    },

    get qualityTodo() {
        return (this.state.job?.extra.quality || []).filter((check) => check.state === "todo").length;
    },

    async openQualityChecks(check) {
        await this.saveNotes();
        const action = await this.orm.call("project.task", "fs_mobile_quality_action", [
            [this.state.job.id],
            check ? check.id : false,
        ]);
        await this.action.doAction(action, { onClose: () => this.reloadJob() });
    },
});
