import { registry } from "@web/core/registry";
import { GanttArchParser } from "./gantt_arch_parser";
import { GanttController } from "./gantt_controller";
import { GanttModel } from "./gantt_model";
import { GanttRenderer } from "./gantt_renderer";

export const ganttView = {
    type: "gantt",
    ArchParser: GanttArchParser,
    Controller: GanttController,
    Model: GanttModel,
    Renderer: GanttRenderer,
    buttonTemplate: "om_web_gantt.GanttController.Buttons",
    searchMenuTypes: ["filter", "groupBy", "favorite"],

    props: (genericProps, view) => {
        const { ArchParser, Model, Renderer, buttonTemplate: viewButtonTemplate } = view;
        const { arch, relatedModels, resModel, buttonTemplate } = genericProps;
        return {
            ...genericProps,
            archInfo: new ArchParser().parse(arch, relatedModels, resModel),
            buttonTemplate: buttonTemplate || viewButtonTemplate,
            Model,
            Renderer,
        };
    },
};

registry.category("views").add("gantt", ganttView);
