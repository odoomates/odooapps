import { serializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ganttView } from "@om_web_gantt/gantt_view";
import { GanttController } from "@om_web_gantt/gantt_controller";

export class PlanningGanttController extends GanttController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get planningRange() {
        const range = this.model.data.range;
        return {
            start: serializeDateTime(range.start),
            stop: serializeDateTime(range.stop),
        };
    }

    async onClickCopyPrevious() {
        const { start, stop } = this.planningRange;
        const count = await this.orm.call(
            this.props.resModel,
            "action_copy_previous",
            [start, stop, this.model.scale, this.model.meta.domain],
            { context: this.model.meta.context }
        );
        this.notification.add(
            count
                ? _t("%s slots copied from the previous period.", count)
                : _t("Nothing to copy from the previous period."),
            { type: count ? "success" : "info" }
        );
        await this.model.load();
    }

    async onClickPublish() {
        const { start, stop } = this.planningRange;
        const action = await this.orm.call(this.props.resModel, "action_publish_period", [
            start,
            stop,
            this.model.meta.domain,
        ]);
        await this.actionService.doAction(action, {
            onClose: () => this.model.load(),
        });
    }

    async onClickRotation() {
        await this.actionService.doAction("om_planning.action_om_planning_rotation_apply", {
            additionalContext: { default_date_from: this.model.data.range.start.toISODate() },
            onClose: () => this.model.load(),
        });
    }
}

export const planningGanttView = {
    ...ganttView,
    Controller: PlanningGanttController,
    buttonTemplate: "om_planning.PlanningGanttButtons",
};

registry.category("views").add("om_planning_gantt", planningGanttView);
