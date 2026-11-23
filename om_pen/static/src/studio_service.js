import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

// the view types the Studio edits; any other screen opens it on the form
export const STUDIO_VIEW_TYPES = [
    "form",
    "list",
    "kanban",
    "search",
    "calendar",
    "pivot",
    "graph",
    "activity",
];

/**
 * Opens the Studio on what is on screen: the model, the view type and the record
 * of the current window action. On a screen with nothing to customize, it opens
 * on the app builder instead.
 */
export const penStudioService = {
    dependencies: ["action"],

    async start(env, { action }) {
        const allowed = await user.hasGroup("om_pen.group_customizer");
        if (allowed) {
            registry
                .category("systray")
                .add("om_pen.studio", { Component: PenStudioSystray }, { sequence: 50 });
        }

        function currentContext() {
            const controller = action.currentController;
            const act = controller?.action;
            if (!act || act.type !== "ir.actions.act_window" || !controller.props?.resModel) {
                return { model: false, actionId: act?.id || false };
            }
            const { props } = controller;
            const viewType = STUDIO_VIEW_TYPES.includes(props.type) ? props.type : "form";
            const views = {};
            for (const [viewId, type] of act.views || []) {
                views[type] = viewId || false;
            }
            return {
                model: props.resModel,
                viewType,
                viewId: views[viewType] || false,
                actionId: act.id || false,
                resId: props.type === "form" ? controller.currentState?.resId || props.resId || false : false,
            };
        }

        return {
            allowed,
            currentContext,
            open(params = currentContext()) {
                return action.doAction({
                    type: "ir.actions.client",
                    tag: "om_pen.studio",
                    name: "Pen Studio",
                    params,
                    target: "current",
                });
            },
        };
    },
};

registry.category("services").add("om_pen_studio", penStudioService);

export class PenStudioSystray extends Component {
    static template = "om_pen.StudioSystray";
    props = useProps();

    setup() {
        this.studio = useService("om_pen_studio");
    }
}
